CREATE OR REPLACE FUNCTION rep.bill_doc_details_f(
    bill_no integer,
    doc     text,
    usr     integer DEFAULT 0,
    OUT "Фирма"              character varying,
    OUT "Счет"               integer,
    OUT "Накладная"          date,
    OUT "Фактура"            character varying,
    OUT "ФактураДата"        date,
    OUT "АвансФактураДата"   date,
    OUT "ПродавецРекв"       character varying,
    OUT "ПродавецБанк"       character varying,
    OUT "Плательщик"         character varying,
    OUT "Грузополучатель"    character varying,
    OUT "НомерГосКонтракта"  character varying,
    OUT "ФТелефон"           character varying,
    OUT "ФОКПО"              character varying,
    OUT "РОКПО"              character varying,
    OUT "ГОКПО"              character varying,
    OUT "ЗаБухгалтера"       character varying,
    OUT "ЗаДиректора"        character varying,
    OUT "ДовЗаБухгалтера"    character varying,
    OUT "ДовЗаДиректора"     character varying,
    OUT "Должность"          character varying,
    OUT "СтавкаНДС"          integer,
    OUT "Основание"          character varying,
    OUT "ФЮрНазвание"        character varying,
    OUT "ФЮрАдрес"           character varying,
    OUT "ФИНН"               character varying,
    OUT "ФКПП"               character varying,
    OUT "РЮрНазвание"        character varying,
    OUT "РЮрАдрес"           character varying,
    OUT "РИНН"               character varying,
    OUT "РКПП"               character varying,
    OUT "Префикс"            character varying,
    OUT "Печать"             character varying,
    OUT "Страна"             character varying,
    OUT dogovor              character varying,
    OUT avans                character varying,
    OUT bill_pp              character varying
)
RETURNS SETOF record
LANGUAGE plpgsql
AS $function$
DECLARE
    j    jsonb;
    d    jsonb;
    s    jsonb;
    b    jsonb;
    c    jsonb;
    sig  jsonb;
    ct   jsonb;

    v_tmp   varchar;
    v_payer varchar;
    v_cargo varchar;
    v_basis varchar;
    v_inv   date;
    v_num   varchar;
BEGIN
    j := rep.bill_doc_details_j(bill_no, doc, usr);
    d   := j->'document';
    s   := j->'seller';
    b   := j->'buyer';
    c   := j->'consignee';
    sig := j->'signatures';
    ct  := j->'contracts';

    ----------------------------------------------------------------
    -- Прямые поля
    ----------------------------------------------------------------
    "Фирма"             := d->>'firm';
    "Счет"              := bill_no;

    -- Накладная = ДатаСчета для 'Счет'/'СчетФакс', иначе rs.Накладная
    IF doc IN ('Счет','СчетФакс') THEN
        v_inv := (d->>'bill_date')::date;
    ELSE
        v_inv := (d->>'invoice_date_raw')::date;
    END IF;
    "Накладная" := v_inv;

    -- Фактура: COALESCE(NULLIF(sf_num,''), "№ Фактуры")
    "Фактура" := COALESCE(NULLIF(d->>'sf_num',''), d->>'invoice_num_raw');

    "ФактураДата"       := (d->>'factura_date')::date;
    "АвансФактураДата"  := (d->>'advance_invoice_date')::date;
    "НомерГосКонтракта" := ct->>'state_contract_number';
    "СтавкаНДС"         := (d->>'vat_rate')::integer;
    "Префикс"           := d->>'prefix';
    "Страна"            := d->>'country';
    "Печать"            := sig->>'stamp';

    ----------------------------------------------------------------
    -- Продавец
    ----------------------------------------------------------------
    v_tmp := COALESCE(s->>'legal_name','') || ', ' ||
             COALESCE(s->>'legal_address','') || E'\n' ||
             'ИНН: ' || (s->>'inn');
    IF (s->>'kpp') IS NOT NULL THEN
        v_tmp := v_tmp || ' КПП: ' || (s->>'kpp');
    END IF;
    IF (s->>'ogrn') IS NOT NULL THEN
        v_tmp := v_tmp || ' ОГРН:' || (s->>'ogrn');
    END IF;
    "ПродавецРекв" := v_tmp;

    "ПродавецБанк" := 'Расчетный счет ' || (s->>'rs') ||
                      ' в ' || (s->>'bank') || ', ' ||
                      (s->>'bank_city') || ', БИК: ' || (s->>'bik');

    "ФТелефон" := s->>'phone';
    "ФОКПО"    := s->>'okpo';
    "ФЮрНазвание" := s->>'legal_name';
    "ФЮрАдрес"    := s->>'legal_address';
    "ФИНН"        := s->>'inn';
    "ФКПП"        := s->>'kpp';

    ----------------------------------------------------------------
    -- Плательщик и грузополучатель
    ----------------------------------------------------------------
    IF (b->>'is_worker')::boolean THEN
        v_payer := b->>'worker_fio';
        v_cargo := b->>'worker_fio';
    ELSE
        -- Плательщик
        v_payer := COALESCE(b->>'legal_name','') || ', ' ||
                   COALESCE(b->>'legal_address','');
        IF (b->>'inn') IS NOT NULL THEN
            v_payer := v_payer || E'\n' || 'ИНН: ' || (b->>'inn');
        END IF;
        IF (b->>'kpp') IS NOT NULL THEN
            v_payer := v_payer || ' КПП: ' || (b->>'kpp');
        END IF;
        -- ОГРН в исходнике не включался — не включаем и здесь
        IF (b->>'rs') IS NOT NULL AND (b->>'bank') IS NOT NULL THEN
            v_payer := v_payer || E' ' || 'р/с ' || (b->>'rs') ||
                       ' в ' || (b->>'bank');
        END IF;
        IF (b->>'ks') IS NOT NULL THEN
            v_payer := v_payer || ', к/с' || (b->>'ks');
        END IF;
        IF (b->>'bik') IS NOT NULL THEN
            v_payer := v_payer || ', БИК' || (b->>'bik');
        END IF;

        -- Грузополучатель
        IF (c->>'code') IS NOT NULL THEN
            -- был код в справочнике Грузополучатель
            v_cargo := c->>'address';
            "ГОКПО" := c->>'okpo';
        ELSE
            v_cargo := b->>'gp';
            IF v_cargo IS NULL AND (b->>'legal_address') IS NOT NULL THEN
                v_cargo := (b->>'legal_name') || ' Адрес: ' || (b->>'legal_address');
            END IF;
            IF doc = 'Накладная' THEN
                IF (b->>'inn') IS NOT NULL THEN
                    v_cargo := v_cargo || ' ИНН: ' || (b->>'inn');
                END IF;
                IF (b->>'kpp') IS NOT NULL THEN
                    v_cargo := v_cargo || ' КПП: ' || (b->>'kpp');
                END IF;
                IF (b->>'rs') IS NOT NULL AND (b->>'bank') IS NOT NULL THEN
                    v_cargo := v_cargo || ' ' || 'р/с ' || (b->>'rs') ||
                               ' в ' || (b->>'bank');
                END IF;
                IF (b->>'ks') IS NOT NULL THEN
                    v_cargo := v_cargo || ', к/с' || (b->>'ks');
                END IF;
                IF (b->>'bik') IS NOT NULL THEN
                    v_cargo := v_cargo || ', БИК' || (b->>'bik');
                END IF;
            END IF;
        END IF;

        "РОКПО"        := b->>'okpo';
        "РЮрНазвание"  := b->>'legal_name';
        "РЮрАдрес"     := b->>'legal_address';
        "РИНН"         := b->>'inn';
        "РКПП"         := b->>'kpp';
    END IF;

    "Плательщик"      := v_payer;
    "Грузополучатель" := v_cargo;

    ----------------------------------------------------------------
    -- Подписи
    ----------------------------------------------------------------
    "ЗаБухгалтера"    := sig->>'accountant';
    "ЗаДиректора"     := sig->>'director';
    "ДовЗаБухгалтера" := sig->>'attorney_accountant';
    "ДовЗаДиректора"  := sig->>'attorney_director';
    "Должность"       := sig->>'position';

    ----------------------------------------------------------------
    -- Основание
    ----------------------------------------------------------------
    IF (d->>'basis_from_bill') IS NOT NULL THEN
        v_basis := d->>'basis_from_bill';
    ELSE
        v_basis := trim(
            COALESCE(trim(s->>'prefix_invoice'), '') ||
            CASE
                WHEN length(COALESCE((d->>'parent_bill')::integer, bill_no)::text) = 8
                    THEN to_char(COALESCE((d->>'parent_bill')::integer, bill_no),
                                 '0000-0000'::varchar)
                WHEN length(COALESCE((d->>'parent_bill')::integer, bill_no)::text) = 9
                    THEN to_char(COALESCE((d->>'parent_bill')::integer, bill_no),
                                 '0000-00000'::varchar)
            END::text ||
            ' от ' || to_char(COALESCE((d->>'parent_date')::date, now()), 'dd.mm.yyyy')
        );
    END IF;
    "Основание" := v_basis;

    ----------------------------------------------------------------
    -- dogovor
    ----------------------------------------------------------------
    IF (ct->>'dogovor_number') IS NOT NULL OR (ct->>'dogovor_type') IS NOT NULL THEN
        v_num := CASE
            WHEN (ct->>'dogovor_type')::int = 4 THEN 'Договор №'
            WHEN (ct->>'dogovor_type')::int IN (1,2,5) THEN 'Договор поставки №'
            WHEN (ct->>'dogovor_type')::int = 6 THEN 'Договор-счет №'
            ELSE 'Договор №'
        END;
        dogovor := v_num || (ct->>'dogovor_number') || ' от ' ||
                   to_char((ct->>'dogovor_date')::date, 'dd.mm.yyyy');
    ELSE
        dogovor := NULL;
    END IF;

    ----------------------------------------------------------------
    -- avans / bill_pp: собираем строки как в исходнике
    ----------------------------------------------------------------
    SELECT string_agg(
               format('№ %s от %s исправление №- от -',
                      e->>'num',
                      to_char((e->>'date')::date, 'DD.MM.YYYY')),
               '; ')
    INTO avans
    FROM jsonb_array_elements(ct->'avans_list') e;

    SELECT string_agg(
               format('%s от %s',
                      e->>'num',
                      to_char((e->>'date')::date, 'DD.MM.YYYY')),
               ', ')
    INTO bill_pp
    FROM jsonb_array_elements(ct->'bill_pp_list') e;

    RETURN NEXT;
END;
$function$;
