CREATE OR REPLACE FUNCTION ext.get_edo_ids(
    arg_inn varchar, arg_kpp varchar DEFAULT NULL) RETURNS character varying
    LANGUAGE plpgsql
    AS $$
DECLARE cmd character varying;
  ret_str VARCHAR := '';
  err_str VARCHAR := '';
  prj_name text := 'astral.doki';   
  wrk_dir text ;
  venv_dir text := '/opt/venvs';
  loc_app_srv varchar;
BEGIN
    wrk_dir := format('/opt/%s', prj_name);
    cmd := format('cd %s; %s/%s/bin/python ./astral_doki.py --log-file=%s/astral_doki.log --inn=%s', 
        wrk_dir,
        venv_dir,
        prj_name,
        wrk_dir, -- logfile dir
        arg_inn
        );

    IF arg_kpp IS NOT NULL THEN
        cmd := format('%s --kpp %s', cmd, arg_kpp);
    END IF;

    IF cmd IS NULL THEN 
       err_str := 'get_edo_ids cmd IS NULL';
       RAISE '%', err_str ; 
    END IF;

    loc_app_srv := arc_energo.arc_const('astral_server');
    RAISE NOTICE 'loc_app_srv =%', loc_app_srv ; 
    -- SELECT * FROM public.exec_ssh(loc_app_srv, '22', 'apps', cmd) INTO ret_str, err_str ;
    SELECT * FROM public.exec_paramiko(loc_app_srv, '22', 'apps', cmd) INTO ret_str, err_str ;
    
    IF err_str IS NOT NULL AND err_str <> ''
    THEN 
       RAISE 'astral_doki cmd=%^err_str=[%]', cmd, err_str; 
       --ret_str := format('%s/%s', ret_str, err_str);
       ret_str := err_str;
    END IF;

    -- parse and save


    return ret_str;
END;$$;

