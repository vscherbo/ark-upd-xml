SELECT rep.test_bill_doc_details_ok(
    (SELECT array_agg(b."№ счета")
     FROM (
         SELECT "№ счета", dt_create
         FROM arc_energo."Счета"
         WHERE фирма <> 'ИПРО'
           AND "Накладная" IS NOT NULL
           AND "№ Фактуры" IS NOT NULL
           AND dt_create IS NOT NULL
         ORDER BY dt_create DESC
         LIMIT 3
     ) AS b),
    'УПД_ОСЗ') AS test_passed;


SELECT *
FROM rep.test_bill_doc_details_compare(
    ARRAY[66230034, 66230035, 66230036],
    'Накладная',
    124
);


SELECT *
FROM rep.test_bill_doc_details_compare(
        ARRAY[66230034, 66230035], 'Накладная', 124)
UNION ALL
SELECT *
FROM rep.test_bill_doc_details_compare(
        ARRAY[66230034, 66230035], 'Счет', 124)
UNION ALL
SELECT *
FROM rep.test_bill_doc_details_compare(
        ARRAY[66230034, 66230035], 'СчетФакс', 124)
UNION ALL
SELECT *
FROM rep.test_bill_doc_details_compare(
        ARRAY[66230034, 66230035], 'УПД_ОСЗ', 124);

