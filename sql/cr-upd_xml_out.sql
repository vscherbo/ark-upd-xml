-- 
DROP FUNCTION arc_energo.upd_xml(integer, varchar);

CREATE OR REPLACE FUNCTION arc_energo.upd_xml(
    arg_bill_no integer,
    arg_edo_prefix varchar(3) DEFAULT '2LT',
    OUT out_filename text,
    OUT out_error   text
)
AS $$
DECLARE
    cmd         varchar;
    ret_str     varchar := '';
    err_str     varchar := '';
    wrk_dir     text := '/opt/astral.doki';
    loc_app_srv varchar;
BEGIN
    cmd := format(
        'cd %s; /home/apps/.pyenv/versions/3.13.0/bin/python %s/cli_client.py --bill-number %s --edo-prefix %s --log-level DEBUG --log-file=%s/upd_xml.log',
        wrk_dir, wrk_dir, arg_bill_no, arg_edo_prefix, wrk_dir
    );

    IF cmd IS NULL THEN
        out_error := 'upd_xml cmd IS NULL';
        RETURN;
    END IF;

    loc_app_srv := arc_energo.arc_const('astral_server');

    SELECT * FROM public.exec_paramiko(loc_app_srv, '22', 'apps', cmd)
      INTO ret_str, err_str;

    IF err_str IS NOT NULL AND err_str <> '' THEN
        out_filename := NULL;
        out_error    := err_str;
        RETURN;
    END IF;

    -- успех: скрипт вернул имя файла в ret_str
    out_filename := ret_str;
    out_error    := NULL;
END;
$$ LANGUAGE plpgsql;


/** Примеры: SQL
-- Получить обе колонки
SELECT * FROM arc_energo.upd_xml(12345);

-- Или только имя файла, если ошибка не интересует
SELECT out_filename
FROM arc_energo.upd_xml(12345)
WHERE out_error IS NULL;

******* plpgsql
DECLARE
    v_filename text;
    v_error    text;
BEGIN
    SELECT out_filename, out_error
      INTO v_filename, v_error
      FROM arc_energo.upd_xml(12345);

    IF v_error IS NOT NULL THEN
        RAISE NOTICE 'Ошибка: %', v_error;
    ELSE
        RAISE NOTICE 'XML создан: %', v_filename;
    END IF;
END;
**/


