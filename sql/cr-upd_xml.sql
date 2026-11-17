CREATE OR REPLACE FUNCTION arc_energo.upd_xml(arg_bill_ni integer, arg_edo_prefix varchar(3) DEFAULT '2LT')
  RETURNS character varying -- err_str OR empty str
AS
$BODY$
DECLARE cmd character varying;
  ret_str VARCHAR := '';
  err_str VARCHAR := '';
  wrk_dir text := '/opt/astral.doki';
  loc_app_srv varchar;
BEGIN
    cmd := format('python %s/ark_upd_xml.py --bill-number %s --edo-prefix %s --log_file=%s/upd_xml.log', 
       wrk_dir, -- script dir
       arg_bill_no,
       arg_edo_prefix, 
       wrk_dir -- logfile dir
       );

    IF cmd IS NULL 
    THEN 
       err_str := 'upd_xml cmd IS NULL';
       RAISE '%', err_str ; 
    END IF;

    loc_app_srv := arc_energo.arc_const('astral_server');
    SELECT * FROM public.exec_paramiko(loc_app_srv, '22', 'apps', cmd) INTO ret_str, err_str ;
    
    IF err_str IS NOT NULL AND err_str <> ''
    THEN 
       RAISE 'upd_xml cmd=%^err_str=[%]', cmd, err_str; 
       --ret_str := format('%s/%s', ret_str, err_str);
       ret_str := err_str;
    END IF;
    
    return ret_str;
END;$BODY$
  LANGUAGE plpgsql VOLATILE
  COST 100;
