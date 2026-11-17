CREATE OR REPLACE FUNCTION rep.test_bill_doc_details_compare(
    p_bills integer[],
    p_doc   text    DEFAULT 'Накладная',
    p_usr   integer DEFAULT 0
)
RETURNS TABLE (
    bill_no    integer,
    doc        text,
    field_name text,
    old_value  text,
    new_value  text
)
LANGUAGE plpgsql
AS $function$
DECLARE
    v_bill        integer;
    r_old         record;
    r_new         record;
    j_old         jsonb;
    j_new         jsonb;
    k             text;
    v_old         text;
    v_new         text;
    v_found_old   boolean;
    v_found_new   boolean;
BEGIN
    FOREACH v_bill IN ARRAY p_bills LOOP
        j_old := NULL;
        j_new := NULL;

        -- 1. Старая функция
        SELECT * INTO r_old FROM rep.bill_doc_details(v_bill, p_doc, p_usr);
        v_found_old := FOUND;
        IF v_found_old THEN
            j_old := to_jsonb(r_old);
        END IF;

        -- 2. Новая обёртка
        SELECT * INTO r_new FROM rep.bill_doc_details_f(v_bill, p_doc, p_usr);
        v_found_new := FOUND;
        IF v_found_new THEN
            j_new := to_jsonb(r_new);
        END IF;

        -- 3. Обе вернули пусто — сравнивать нечего
        IF NOT v_found_old AND NOT v_found_new THEN
            CONTINUE;
        END IF;

        -- 4. Одна вернула строку, другая — нет
        IF v_found_old <> v_found_new THEN
            bill_no    := v_bill;
            doc        := p_doc;
            field_name := '<row_presence>';
            old_value  := CASE WHEN v_found_old THEN 'present' ELSE 'absent' END;
            new_value  := CASE WHEN v_found_new THEN 'present' ELSE 'absent' END;
            RETURN NEXT;
            CONTINUE;
        END IF;

        -- 5. Поэлементное сравнение по объединению ключей
        FOR k IN
            SELECT DISTINCT key
            FROM (
                SELECT jsonb_object_keys(j_old) AS key
                UNION
                SELECT jsonb_object_keys(j_new) AS key
            ) t
            ORDER BY key
        LOOP
            v_old := j_old->>k;
            v_new := j_new->>k;

            IF v_old IS DISTINCT FROM v_new THEN
                bill_no    := v_bill;
                doc        := p_doc;
                field_name := k;
                old_value  := v_old;
                new_value  := v_new;
                RETURN NEXT;
            END IF;
        END LOOP;
    END LOOP;
END;
$function$;


CREATE OR REPLACE FUNCTION rep.test_bill_doc_details_ok(
    p_bills integer[],
    p_doc   text    DEFAULT 'Накладная',
    p_usr   integer DEFAULT 0
)
RETURNS boolean
LANGUAGE sql
AS $function$
    SELECT NOT EXISTS (
        SELECT 1
        FROM rep.test_bill_doc_details_compare(p_bills, p_doc, p_usr)
    );
$function$;
