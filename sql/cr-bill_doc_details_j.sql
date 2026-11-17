CREATE OR REPLACE FUNCTION rep.bill_doc_details_j(
    bill_no integer,
    doc     text,
    usr     integer DEFAULT 0
)
RETURNS jsonb
LANGUAGE plpgsql
AS $function$
DECLARE
    rs           RECORD;
    parent_bill  INTEGER;
    parent_date  DATE;
    kg           INTEGER;
    kr           INTEGER;
    kodp         INTEGER;
    f_req        INTEGER;
    loc_sign_emp INTEGER;
    v_sign_date  DATE;

    -- документ (сырые данные)
    v_firm_initial         varchar;
    v_firm                 varchar;
    v_bill_date            date;
    v_invoice_date_raw     date;
    v_sf_num               varchar;
    v_invoice_num_raw      varchar;
    v_factura_date         date;
    v_advance_invoice_date date;
    v_basis_from_bill      varchar;
    v_vat_rate             integer;
    v_prefix               varchar;
    v_country              varchar;
    v_own                  integer;

    -- продавец
    v_s_legal_name       varchar;
    v_s_legal_address    varchar;
    v_s_inn              varchar;
    v_s_kpp              varchar;
    v_s_ogrn             varchar;
    v_s_phone            varchar;
    v_s_okpo             varchar;
    v_s_rs               varchar;
    v_s_bank             varchar;
    v_s_bank_city        varchar;
    v_s_bik              varchar;
    v_s_prefix_invoice   varchar;
    v_s_firm_key         varchar;
    v_s_req_id           integer;

    -- покупатель
    v_b_is_worker        boolean := false;
    v_b_worker_fio       varchar;
    v_b_legal_name       varchar;
    v_b_legal_address    varchar;
    v_b_inn              varchar;
    v_b_kpp              varchar;
    v_b_ogrn             varchar;
    v_b_bank             varchar;
    v_b_bik              varchar;
    v_b_rs               varchar;
    v_b_ks               varchar;
    v_b_okpo             varchar;
    v_b_gp               varchar;
    v_b_legal_full_name  varchar;

    -- грузополучатель
    v_c_code    integer;
    v_c_address varchar;
    v_c_okpo    varchar;

    -- подписи
    v_sig_accountant          varchar;
    v_sig_director            varchar;
    v_sig_attorney_accountant varchar;
    v_sig_attorney_director   varchar;
    v_sig_position            varchar;
    v_sig_stamp               varchar;

    -- договоры / платежи
    v_state_contract_number varchar;
    v_dogovor_number        varchar;
    v_dogovor_date          date;
    v_dogovor_type          integer;
    v_avans                 jsonb;
    v_bill_pp               jsonb;

    -- МЧД
    v_mchd_uuid           uuid;
    v_mchd_number         varchar;
    v_mchd_issue_date     date;
    v_mchd_inner_number   varchar;
    v_mchd_inner_reg_date date;
    v_mchd_storage_id     varchar;
    v_mchd_system_url     varchar;
BEGIN
    ----------------------------------------------------------------
    -- 1. Первичный счёт
    ----------------------------------------------------------------
    SELECT s.фирма, s."№ счета", s.Накладная, s."Дата счета", s."№ Фактуры",
           s.sf_num, s.Фактура, s.КодРеквизитов,
           rq.КодРеквизитов AS bank_details, s.КодГрузополучателя,
           s.НомерГосКонтракта, s.Код, s.Префикс, s.Хозяин, s.Основание,
           s.КодРеквизитовФирмы, p.Республика
    INTO rs
    FROM Счета s
    JOIN Предприятия p ON s.Код = p.Код
    LEFT JOIN Реквизиты rq ON s.bank_details = rq.КодРеквизитов
    WHERE s."№ счета" = bill_no;

    v_firm_initial         := rs.фирма;
    v_firm                 := rs.фирма;
    v_country              := rs.Республика;
    v_bill_date            := rs."Дата счета";
    v_invoice_date_raw     := rs.Накладная;
    v_sf_num               := rs.sf_num;
    v_invoice_num_raw      := rs."№ Фактуры";
    v_factura_date         := rs.Фактура;
    v_prefix               := rs.Префикс;
    v_own                  := rs.Хозяин;
    kodp                   := rs.Код;

    IF COALESCE(rs.Основание,'') <> '' AND doc IN ('Накладная','УПД_ОСЗ', 'ЭДО') THEN
        v_basis_from_bill := rs.Основание;
    END IF;

    -- Дата, по которой определяется подпись/ставка
    v_sign_date := CASE WHEN doc IN ('Счет','СчетФакс')
                        THEN rs."Дата счета" ELSE rs.Накладная END;

    v_vat_rate := arc_energo.vat_rate(rs.фирма, rs.Код, v_sign_date);
    v_state_contract_number := rs.НомерГосКонтракта;

    ----------------------------------------------------------------
    -- 2. Дата авансовой фактуры
    ----------------------------------------------------------------
    SELECT max(bi.ФактураНаАвансДата) INTO v_advance_invoice_date
    FROM Счета s
    LEFT JOIN ОплатыНТУ op ON s."№ счета" = op.Счет
    LEFT JOIN БанкИмпорт bi ON op.КодЗаписи = bi.КодЗаписи
    WHERE s."№ счета" = bill_no;

    ----------------------------------------------------------------
    -- 3. Код грузополучателя
    ----------------------------------------------------------------
    kg := rs.КодГрузополучателя;
    PERFORM КодГрузополучателя FROM Грузополучатель WHERE КодГрузополучателя = kg;
    IF NOT FOUND THEN
        kg := NULL;
        UPDATE Счета SET КодГрузополучателя = NULL WHERE "№ счета" = bill_no;
    END IF;
    v_c_code := kg;

    ----------------------------------------------------------------
    -- 4. Код реквизитов контрагента и parent-счёт
    ----------------------------------------------------------------
    kr := COALESCE(rs.bank_details, rs.КодРеквизитов);

    IF POSITION('66' IN bill_no::text) > 0 AND length(bill_no::text) = 8 THEN
        SELECT предок INTO parent_bill FROM Счета WHERE "№ счета" = bill_no;
    ELSE
        parent_bill := bill_no;
    END IF;

    SELECT CASE WHEN kr IS NULL THEN COALESCE(bank_details, КодРеквизитов) ELSE kr END,
           s.НомерГосКонтракта, s."Дата счета"
    INTO kr, v_state_contract_number, parent_date
    FROM Счета s WHERE "№ счета" = parent_bill;

    ----------------------------------------------------------------
    -- 5. Реквизиты фирмы (продавца)
    ----------------------------------------------------------------
    IF rs.КодРеквизитовФирмы IS NULL THEN
        SELECT firma_id INTO f_req
        FROM arc_energo.bill_get_firma_id(bill_no, rs.фирма);
        UPDATE Счета SET КодРеквизитовФирмы = f_req WHERE "№ счета" = bill_no;
    ELSE
        f_req := rs.КодРеквизитовФирмы;
    END IF;

    -- Корректировка для старых счетов
    IF v_sign_date < '2022-07-26'
       AND doc IN ('Счет','СчетФакс')
       AND f_req IN (164,163) THEN
        f_req := CASE WHEN f_req = 164 THEN 152
                      WHEN f_req = 163 THEN 160
                      ELSE NULL END;
    END IF;
    v_s_req_id := f_req;

    SELECT fr.Ф_НазваниеКратко, fr.Ф_ЮрАдрес, f.Ф_ИНН, fr.Ф_КПП, f.Ф_ОГРН,
           fr.Ф_РассчетныйСчет, fr.Ф_Банк, fr.Ф_ГородБанка, fr.Ф_БИК,
           fr.Ф_Телефон, COALESCE(fr.Ф_ОКПО, f.Ф_ОКПО),
           f.ПрефиксВСчет, fr.КодФирмы
    INTO v_s_legal_name, v_s_legal_address, v_s_inn, v_s_kpp, v_s_ogrn,
         v_s_rs, v_s_bank, v_s_bank_city, v_s_bik,
         v_s_phone, v_s_okpo, v_s_prefix_invoice, v_s_firm_key
    FROM Фирма f
    JOIN ФирмаРеквизиты fr ON f.КлючФирмы::text = fr.КодФирмы
    WHERE fr.КодРеквизитовФирмы = f_req;

    -- Воспроизводим исходное: Фирма := rs.КодФирмы, если отличалось
    IF v_firm_initial <> v_s_firm_key THEN
        v_firm := v_s_firm_key;
    END IF;

    ----------------------------------------------------------------
    -- 6. Покупатель / грузополучатель
    ----------------------------------------------------------------
    IF kodp = 223719 THEN
        -- Особый случай: плательщик и грузополучатель — ФИО работника
        v_b_is_worker := true;
        SELECT Работники.ФИО INTO v_b_worker_fio
        FROM Счета
        JOIN Работники ON Счета.КодРаботника = Работники.КодРаботника
        WHERE Счета."№ счета" = bill_no;
        -- v_c_* остаются NULL, v_b_* (кроме is_worker/worker_fio) — NULL
    ELSE
        SELECT r.ЮрНазвание, r.ЮрАдрес, p.ИНН, r.КПП, p.ОГРН,
               r.Банк, r.БИК, r.Р_счет, r.К_счет,
               COALESCE(r.Грузополучатель, p.Грузополучатель),
               COALESCE(r.ОКПО, p.ОКПО),
               p.ЮрНазваниеПолн
        INTO v_b_legal_name, v_b_legal_address, v_b_inn, v_b_kpp, v_b_ogrn,
             v_b_bank, v_b_bik, v_b_rs, v_b_ks,
             v_b_gp, v_b_okpo, v_b_legal_full_name
        FROM Предприятия p
        JOIN Реквизиты r ON p.Код = r.Код
        WHERE КодРеквизитов = kr;

        IF kg IS NOT NULL THEN
            SELECT Адрес, ОКПО INTO v_c_address, v_c_okpo
            FROM Грузополучатель WHERE КодГрузополучателя = kg;
        END IF;
    END IF;

    ----------------------------------------------------------------
    -- 7. Подписи (+ МЧД через Подписи.uuid)
    ----------------------------------------------------------------
    IF is_gov_holiday(v_sign_date) THEN
        loc_sign_emp := 226;
    ELSE
        loc_sign_emp := usr;
    END IF;

    SELECT p."ЗаДиректора", p."ЗаБухгалтера",
           p."ВидНомерДатаДокументаБух", p."ВидНомерДатаДокументаДир",
           p."Должность", p."stamp_n_sign",
           p.uuid                                     AS mchd_uuid,
           m."НомДовер"::text                         AS mchd_number,
           m."ДатаВыдДовер"                           AS mchd_issue_date,
           m."ВнНомДовер"                             AS mchd_inner_number,
           m."ДатаВнРегДовер"                         AS mchd_inner_reg_date,
           m."ИдСистХран"                             AS mchd_storage_id,
           m."СведСист"                               AS mchd_system_url
    INTO v_sig_director, v_sig_accountant,
         v_sig_attorney_accountant, v_sig_attorney_director,
         v_sig_position, v_sig_stamp,
         v_mchd_uuid,
         v_mchd_number, v_mchd_issue_date,
         v_mchd_inner_number, v_mchd_inner_reg_date,
         v_mchd_storage_id, v_mchd_system_url
    FROM "Подписи" p
    LEFT JOIN "ПодписиМЧД" m ON m."НомДовер" = p.uuid
    WHERE p."КодОтчета"::text = doc
      AND p."КлючФирмы"::text = v_firm
      AND p."НомерСотрудника" = loc_sign_emp
      AND p."ДатаСтартаПодписи" = (
          SELECT max("ДатаСтартаПодписи")
          FROM "Подписи"
          WHERE "КодОтчета"::text = doc
            AND "КлючФирмы"::text = v_firm
            AND "НомерСотрудника" = loc_sign_emp
            AND "ДатаСтартаПодписи" <= v_sign_date
      );

    IF NOT FOUND THEN
        SELECT p."ЗаДиректора", p."ЗаБухгалтера",
               p."ВидНомерДатаДокументаБух", p."ВидНомерДатаДокументаДир",
               p."Должность", p."stamp_n_sign",
               p.uuid, m."НомДовер"::text, m."ДатаВыдДовер",
               m."ВнНомДовер", m."ДатаВнРегДовер",
               m."ИдСистХран", m."СведСист"
        INTO v_sig_director, v_sig_accountant,
             v_sig_attorney_accountant, v_sig_attorney_director,
             v_sig_position, v_sig_stamp,
             v_mchd_uuid,
             v_mchd_number, v_mchd_issue_date,
             v_mchd_inner_number, v_mchd_inner_reg_date,
             v_mchd_storage_id, v_mchd_system_url
        FROM "Подписи" p
        LEFT JOIN "ПодписиМЧД" m ON m."НомДовер" = p.uuid
        WHERE p."КодОтчета"::text = doc
          AND p."КлючФирмы"::text = v_firm
          AND p."НомерСотрудника" = 0
          AND p."ДатаСтартаПодписи" = (
              SELECT max("ДатаСтартаПодписи")
              FROM "Подписи"
              WHERE "КодОтчета"::text = doc
                AND "КлючФирмы"::text = v_firm
                AND "НомерСотрудника" = 0
                AND "ДатаСтартаПодписи" <= v_sign_date
          );
    END IF;
    ----------------------------------------------------------------
    -- 8. Договор (сырые номер/дата/тип)
    ----------------------------------------------------------------
    v_dogovor_number := NULL;
    v_dogovor_date   := NULL;
    v_dogovor_type   := NULL;

    SELECT d.НомерДоговора, d.ДатаДоговора, d.ВидДоговора
    INTO v_dogovor_number, v_dogovor_date, v_dogovor_type
    FROM Договор d
    WHERE REPLACE(REPLACE(НомерДоговора,'-',''),' ','')::text
              LIKE 'ДС%' || bill_no::text || '%'
      AND ВидДоговора = 6
    LIMIT 1;

    IF NOT FOUND THEN
        SELECT d.НомерДоговора, d.ДатаДоговора, d.ВидДоговора
        INTO v_dogovor_number, v_dogovor_date, v_dogovor_type
        FROM Договор d
        WHERE REPLACE(REPLACE(НомерДоговора,'-',''),' ','')::text
                  LIKE '%' || bill_no::text || '%'
          AND ВидДоговора = 2
        LIMIT 1;
    END IF;

    IF v_dogovor_number IS NULL THEN
        SELECT d.НомерДоговора, d.ДатаДоговора, d.ВидДоговора
        INTO v_dogovor_number, v_dogovor_date, v_dogovor_type
        FROM Договор d
        INNER JOIN ДоговорВиды ON d.ВидДоговора = ДоговорВиды.ВидДоговора
        INNER JOIN Счета s0 ON d.КодПредприятия = s0.Код
        WHERE "№ счета" = bill_no
          AND (
              (d.ВидДоговора IN (1,4,5)
               AND date_trunc('year', ДатаДоговора) = date_trunc('Year', current_date))
              OR (d.ВидДоговора = 3)
              OR (d.ВидДоговора <> 1 AND s0."Дата счета" >= ДатаДоговора)
          )
          AND d.ДатаДоговора = (
              SELECT max(d0.ДатаДоговора) FROM Договор d0
              WHERE d0.КодПредприятия = s0.Код
                AND d0.Фирма::text = s0.фирма
          )
        LIMIT 1;
    END IF;

    ----------------------------------------------------------------
    -- 9. Авансовые СФ (сырой массив)
    ----------------------------------------------------------------
    /**
    WITH t AS (
        SELECT DISTINCT s.фирма, s.предок AS Счет, s.Фактура
        FROM Счета s WHERE предок = bill_no
    ),
    grp AS (
        SELECT t.Счет, fr.Ф_БИК,
               jsonb_agg(jsonb_build_object(
                   'num',  bi.ФактураНаАвансНомер,
                   'date', bi.ФактураНаАвансДата
               ) ORDER BY bi.ФактураНаАвансДата, bi.ФактураНаАвансНомер) AS items
        FROM (
            SELECT op.Счет, b0.КодРеквизитовФирмы,
                   ФактураНаАвансНомер, ФактураНаАвансДата
            FROM БанкИмпорт b0
            JOIN ОплатыНТУ op ON b0.КодЗаписи = op.КодЗаписи
                             AND COALESCE(op.Сумма,0) > 0
                             AND b0.firma::TEXT NOT IN ('АРКОМ','ИПРО')
            WHERE ФактураНаАвансНомер IS NOT NULL
        ) bi
        JOIN t ON bi.Счет = t.Счет
        JOIN ФирмаРеквизиты fr ON bi.КодРеквизитовФирмы = fr.КодРеквизитовФирмы
        WHERE t.Фактура > bi.ФактураНаАвансДата
          AND t.фирма <> 'АРКОМ'
        GROUP BY t.Счет, fr.Ф_БИК
    )
    SELECT items INTO v_avans FROM grp LIMIT 1;
    **/
    WITH t AS (
        SELECT DISTINCT s.фирма, s.предок AS Счет, s.Фактура
        FROM Счета s WHERE предок = bill_no
    )
    SELECT jsonb_agg(
               jsonb_build_object(
                   'num',  bi.ФактураНаАвансНомер,
                   'date', bi.ФактураНаАвансДата
               )
               ORDER BY bi.ФактураНаАвансДата, bi.ФактураНаАвансНомер
           )
    INTO v_avans
    FROM (
        SELECT op.Счет, b0.КодРеквизитовФирмы,
               ФактураНаАвансНомер, ФактураНаАвансДата
        FROM БанкИмпорт b0
        JOIN ОплатыНТУ op ON b0.КодЗаписи = op.КодЗаписи
                         AND COALESCE(op.Сумма,0) > 0
                         AND b0.firma::TEXT NOT IN ('АРКОМ','ИПРО')
        WHERE ФактураНаАвансНомер IS NOT NULL
    ) bi
    JOIN t ON bi.Счет = t.Счет
    JOIN ФирмаРеквизиты fr ON bi.КодРеквизитовФирмы = fr.КодРеквизитовФирмы
    WHERE t.Фактура > bi.ФактураНаАвансДата
      AND t.фирма <> 'АРКОМ';

    ----------------------------------------------------------------
    -- 10. Платёжные поручения (сырой массив)
    ----------------------------------------------------------------
    SELECT jsonb_agg(jsonb_build_object(
               'prd_number',  d.Номер,
               'prd_date', d.ДатаПлатежа::date
           ) ORDER BY d.ДатаПлатежа, d.Номер)
    INTO v_bill_pp
    FROM (
        SELECT DISTINCT bi.Номер, bi.ДатаПлатежа
        FROM ОплатыНТУ op
        JOIN БанкИмпорт bi ON op.КодЗаписи = bi.КодЗаписи AND op.Счет = bill_no
    ) d;

    ----------------------------------------------------------------
    -- 11. Сборка jsonb
    ----------------------------------------------------------------
    RETURN jsonb_build_object(
        'document', jsonb_build_object(
            'bill_no',               bill_no,
            'doc_type',              doc,
            'firm',                  v_firm,
            'bill_date',             v_bill_date,
            'invoice_date_raw',      v_invoice_date_raw,
            'sf_num',                v_sf_num,
            'invoice_num_raw',       v_invoice_num_raw,
            'factura_date',          v_factura_date,
            'advance_invoice_date',  v_advance_invoice_date,
            'basis_from_bill',       v_basis_from_bill,
            'vat_rate',              v_vat_rate,
            'prefix',                v_prefix,
            'country',               v_country,
            'own',                   v_own,
            'parent_bill',           parent_bill,
            'parent_date',           parent_date
        ),
        'seller', jsonb_build_object(
            'legal_name',     v_s_legal_name,
            'legal_address',  v_s_legal_address,
            'inn',            v_s_inn,
            'kpp',            v_s_kpp,
            'ogrn',           v_s_ogrn,
            'phone',          v_s_phone,
            'okpo',           v_s_okpo,
            'rs',             v_s_rs,
            'bank',           v_s_bank,
            'bank_city',      v_s_bank_city,
            'bik',            v_s_bik,
            'prefix_invoice', v_s_prefix_invoice,
            'req_id',         v_s_req_id
        ),
        'buyer', jsonb_build_object(
            'is_worker',      v_b_is_worker,
            'worker_fio',     v_b_worker_fio,
            'legal_name',     v_b_legal_name,
            'legal_full_name',v_b_legal_full_name,
            'legal_address',  v_b_legal_address,
            'inn',            v_b_inn,
            'kpp',            v_b_kpp,
            'ogrn',           v_b_ogrn,
            'bank',           v_b_bank,
            'bik',            v_b_bik,
            'rs',             v_b_rs,
            'ks',             v_b_ks,
            'okpo',           v_b_okpo,
            'gp',             v_b_gp
        ),
        'consignee', jsonb_build_object(
            'code',    v_c_code,
            'address', v_c_address,
            'okpo',    v_c_okpo
        ),
        'signatures', jsonb_build_object(
            'accountant',           v_sig_accountant,
            'director',             v_sig_director,
            'attorney_accountant',  v_sig_attorney_accountant,
            'attorney_director',    v_sig_attorney_director,
            'position',             v_sig_position,
            'stamp',                v_sig_stamp,
            'mchd', CASE
                WHEN v_mchd_uuid IS NULL THEN NULL
                ELSE jsonb_build_object(
                    'number',         v_mchd_number,
                    'issue_date',     to_char(v_mchd_issue_date,     'YYYY-MM-DD'),
                    'inner_number',   v_mchd_inner_number,
                    'inner_reg_date', to_char(v_mchd_inner_reg_date, 'YYYY-MM-DD'),
                    'storage_id',     v_mchd_storage_id,
                    'system_url',     v_mchd_system_url
                )
            END
        ),
        'contracts', jsonb_build_object(
            'state_contract_number', v_state_contract_number,
            'dogovor_number',        v_dogovor_number,
            'dogovor_date',          v_dogovor_date,
            'dogovor_type',          v_dogovor_type,
            'avans_list',            COALESCE(v_avans,   '[]'::jsonb),
            'bill_pp_list',          COALESCE(v_bill_pp, '[]'::jsonb)
        )
    );
END;
$function$;
