-- Получить весь JSON
SELECT rep.bill_doc_details_j(66230034, 'Накладная', 124) AS doc_json;

-- Извлечь отдельные атрибуты в SQL-запросе
WITH d AS (
    SELECT rep.bill_doc_details_j(66230034, 'Накладная', 124) AS j
)
SELECT
    j->'document'->>'firm'        AS firm,
    j->'document'->>'invoice_num' AS invoice_num,
    j->'buyer'->>'payer'          AS payer,
    j->'seller'->>'inn'           AS seller_inn,
    j->'contracts'->>'dogovor'    AS dogovor
FROM d;

-- Отдельные атрибуты
WITH x AS (SELECT rep.bill_doc_details_j(66230034, 'Накладная', 124) AS j)
SELECT
    j->'document'->>'firm'                AS firm,
    j->'document'->>'invoice_num_raw'     AS invoice_num,
    j->'document'->>'sf_num'              AS sf_num,
    j->'seller'->>'inn'                   AS seller_inn,
    j->'seller'->>'ogrn'                  AS seller_ogrn,
    j->'buyer'->>'legal_name'             AS buyer_name,
    j->'buyer'->>'is_worker'              AS is_worker,
    j->'consignee'->>'address'            AS consignee_address,
    j->'contracts'->'avans_list'->0->>'num'  AS first_avans_num,
    j->'contracts'->'bill_pp_list'->0->>'num' AS first_pp_num
FROM x;


DO $$
DECLARE
    v jsonb;
    v_firm varchar;
    v_invoice_num varchar;
BEGIN
    v := rep.bill_doc_details_j(66230034, 'Накладная', 124);
    v_firm := v->'document'->>'firm';
    v_invoice_num := v->'document'->>'invoice_num';
    RAISE NOTICE 'Фирма: %, Накладная: %', v_firm, v_invoice_num;
END $$;

-------------------------- f ------------------------------

-- Получить строку со всеми полями, как раньше
SELECT * FROM rep.bill_doc_details_f(66230034, 'Накладная', 124);

-- Выбрать конкретные поля
SELECT "Фирма", "Фактура", "Плательщик", "ФИНН"
FROM rep.bill_doc_details_f(66230034, 'Накладная', 124);

DO $$
DECLARE
    r record;
BEGIN
    SELECT * INTO r FROM rep.bill_doc_details_f(66230034, 'Накладная', 124);
    RAISE NOTICE 'Фирма: %, Фактура: %', r."Фирма", r."Фактура";
END $$;

