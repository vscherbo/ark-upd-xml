-- DROP FUNCTION rep.bill_doc_details(in int4, in text, in int4, out varchar, out int4, out date, out varchar, out date, out date, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out int4, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar, out varchar);

CREATE OR REPLACE FUNCTION rep.bill_doc_details(bill_no integer, doc text, usr integer DEFAULT 0, OUT "Фирма" character varying, OUT "Счет" integer, OUT "Накладная" date, OUT "Фактура" character varying, OUT "ФактураДата" date, OUT "АвансФактураДата" date, OUT "ПродавецРекв" character varying, OUT "ПродавецБанк" character varying, OUT "Плательщик" character varying, OUT "Грузополучатель" character varying, OUT "НомерГосКонтракта" character varying, OUT "ФТелефон" character varying, OUT "ФОКПО" character varying, OUT "РОКПО" character varying, OUT "ГОКПО" character varying, OUT "ЗаБухгалтера" character varying, OUT "ЗаДиректора" character varying, OUT "ДовЗаБухгалтера" character varying, OUT "ДовЗаДиректора" character varying, OUT "Должность" character varying, OUT "СтавкаНДС" integer, OUT "Основание" character varying, OUT "ФЮрНазвание" character varying, OUT "ФЮрАдрес" character varying, OUT "ФИНН" character varying, OUT "ФКПП" character varying, OUT "РЮрНазвание" character varying, OUT "РЮрАдрес" character varying, OUT "РИНН" character varying, OUT "РКПП" character varying, OUT "Префикс" character varying, OUT "Печать" character varying, OUT "Страна" character varying, OUT dogovor character varying, OUT avans character varying, OUT bill_pp character varying)
 RETURNS SETOF record
 LANGUAGE plpgsql
AS $function$
--
DECLARE 
rs RECORD; 
--firma varchar; nakl DATE;
parent_bill INTEGER;
parent_date DATE;
cargo_receiver VARCHAR;
--
seller_r VARCHAR;
seller_b VARCHAR;
payer VARCHAR;
--
kg INTEGER; /*Код Грузополучателя*/
kr INTEGER; /*Код Реквизитов*/
bd INTEGER; /*bank_details*/
kodp INTEGER;
prefix varchar;
own INTEGER;
dt_bill date;
loc_sign_emp INTEGER DEFAULT 0; 
f_req INTEGER;
--
BEGIN  
/*
SELECT Счет, Фирма, ФТелефон, ФОКПО, РОКПО, Накладная,Фактура,ФактураДата,ПродавецРекв,ПродавецБанк,
Плательщик::varchar(1000),Грузополучатель, НомерГосКонтракта, 
ЗаБухгалтера, ЗаДиректора, ДовЗаБухгалтера, ДовЗаДиректора, Должность, СтавкаНДС, Основание  
FROM rep.bill_doc_details(66230034::integer,'Накладная'::text,124::integer)
2021-12-15 Добавил АвансФактураДата, поскольку есть изменения в расчетах на дату
*/
--
SELECT  фирма, "№ счета", s.Накладная, s."Дата счета", s."№ Фактуры",s.sf_num, s.Фактура, s.КодРеквизитов, rq.КодРеквизитов AS bank_details, s.КодГрузополучателя,
s.НомерГосКонтракта,s.Код, s.Префикс, s.Хозяин, s.Основание, КодРеквизитовФирмы, p.Республика
INTO rs
FROM Счета s 
JOIN Предприятия p ON s.Код=p.Код
LEFT JOIN Реквизиты rq ON  s.bank_details=rq.КодРеквизитов  WHERE "№ счета"=bill_no;
	Страна:=rs.Республика;
--
IF COALESCE(rs.Основание,'')<>'' AND (doc::text='Накладная' OR  doc::text='УПД_ОСЗ') THEN
	Основание:=rs.Основание;
END IF;
--
	IF doc::text = 'Счет' OR doc::text = 'СчетФакс' THEN
		Накладная:= rs."Дата счета";
	/*ELSEIf doc::text = 'Фактура' THEN
	doc:='УПД_ОСЗ';*/
	ELSE 
		Накладная:=rs.Накладная;
	END IF;
--
	СтавкаНДС:=arc_energo.vat_rate(rs.фирма,rs.Код,Накладная::date);
	Фирма:=rs.фирма;
	НомерГосКонтракта:= rs.НомерГосКонтракта;
--
	Фактура:=COALESCE(NULLIF(rs.sf_num,'')::varchar,rs."№ Фактуры"::varchar);
	ФактураДата:=rs.Фактура;
	Префикс:=rs.Префикс;
	own:=rs.Хозяин;
--	
	SELECT max(bi.ФактураНаАвансДата) INTO АвансФактураДата 
	FROM Счета s LEFT JOIN ОплатыНТУ op ON s."№ счета"=op.Счет
	LEFT JOIN БанкИмпорт bi ON op.КодЗаписи=bi.КодЗаписи
	WHERE s."№ счета"=bill_no;
	
	kg:=rs.КодГрузополучателя; /*Код Грузополучателя*/
--	
	PERFORM КодГрузополучателя FROM Грузополучатель WHERE  КодГрузополучателя = kg;
--	
IF NOT FOUND THEN
	kg:= NULL;
	UPDATE Счета SET КодГрузополучателя = NULL  WHERE "№ счета"=bill_no; 
	END IF;
--
	kr:=COALESCE(rs.bank_details,rs.КодРеквизитов); /*Код Реквизитов*/
--	
	RAISE NOTICE  'КР %', kr; 
--	
	kodp:=rs.Код;
	--bd:=rs.bank_details; /*bank_details*/
--
	IF POSITION('66' IN bill_no::text) >0  AND  length(bill_no::text)=8 THEN
		SELECT предок INTO parent_bill FROM Счета WHERE "№ счета" = bill_no;
	ELSE 
		parent_bill:=bill_no;
	END IF;
		/*Проверка кода реквизитов для разбитых счетов: если он уже определен для разбитого счета, не надо его вычислять.*/
		SELECT CASE WHEN kr IS NULL THEN COALESCE(bank_details,КодРеквизитов) ELSE kr END, s.НомерГосКонтракта, "Дата счета" 
		INTO kr, НомерГосКонтракта, parent_date 
		FROM Счета s WHERE "№ счета" = parent_bill;
--	
/*ФИРМА РЕКВИЗИТЫ*/
	/*Реквизиты фирмы*/
	IF rs.КодРеквизитовФирмы IS NULL THEN 
		SELECT firma_id INTO f_req FROM arc_energo.bill_get_firma_id(bill_no, rs.фирма);
		UPDATE Счета SET КодРеквизитовФирмы= f_req WHERE "№ счета"=bill_no;
	ELSE
		f_req:=rs.КодРеквизитовФирмы;
	END IF;
--
	IF Накладная <'2022-07-26' 	AND	(doc::text = 'Счет' OR doc::text = 'СчетФакс')	AND	(f_req=164 OR f_req=163) THEN
			f_req:=CASE WHEN f_req=164 THEN 152 WHEN f_req=163 THEN 160 ELSE NULL END;	
	END IF;
--
	SELECT Ф_НазваниеКратко, Ф_ЮрАдрес, f.Ф_ИНН,f.Ф_КПП, f.Ф_ОГРН,
	Ф_РассчетныйСчет,Ф_Банк,Ф_ГородБанка,Ф_БИК,fr.Ф_Телефон,COALESCE(fr.Ф_ОКПО,f.Ф_ОКПО) ФОКПО, ПрефиксВСчет,
	КодФирмы
	INTO rs
	FROM Фирма f JOIN ФирмаРеквизиты fr ON  f.КлючФирмы::text = fr.КодФирмы 
	WHERE fr.КодРеквизитовФирмы = f_req;
--
	IF Фирма<>rs.КодФирмы THEN
	Фирма:=rs.КодФирмы;
	END IF;
	/*Закомментировал WHERE 19 июля 2021 
	 * КлючФирмы = Фирма AND Ф_ДатаВводаРеквизитов = 
		(SELECT  Max(Ф_ДатаВводаРеквизитов) FROM ФирмаРеквизиты WHERE КодФирмы::text = КлючФирмы AND Ф_ДатаВводаРеквизитов <= Накладная ); */
--
	ФЮрНазвание:=rs.Ф_НазваниеКратко; 
	ФЮрАдрес:=rs.Ф_ЮрАдрес; 
	ФИНН:=rs.Ф_ИНН; 
	ФКПП:=rs.Ф_КПП;
--	
	prefix:=rs.ПрефиксВСчет;
	ФТелефон:= rs.Ф_Телефон;
	ФОКПО:=rs.ФОКПО;
	seller_r:=COALESCE(rs.Ф_НазваниеКратко,'')||', '||COALESCE(rs.Ф_ЮрАдрес,'')||E'\n'||'ИНН: '||rs.Ф_ИНН;  
		IF rs.Ф_КПП  IS NOT NULL THEN seller_r:=seller_r||' КПП: '||rs.Ф_КПП; END IF;  
		IF rs.Ф_ОГРН IS NOT NULL THEN seller_r:=seller_r||' ОГРН:'||rs.Ф_ОГРН; END IF;
	--RAISE NOTICE '%', seller_r;
	ПродавецРекв:=seller_r;
--	
	/*Банковские реквизиты фирмы*/
	seller_b:='Расчетный счет '||rs.Ф_РассчетныйСчет||' в '||rs.Ф_Банк||', '||rs.Ф_ГородБанка||', БИК: '||rs.Ф_БИК;
	ПродавецБанк:=seller_b;	
--
/*РЕКВИЗИТЫ ПЛАТЕЛЬЩИКА*/
IF kodp =223719 THEN
	SELECT Работники.ФИО INTO cargo_receiver FROM Счета JOIN Работники ON Счета.КодРаботника = Работники.КодРаботника
	WHERE Счета."№ счета"= bill_no;
payer:=cargo_receiver;
ELSE 
	SELECT r.ЮрНазвание, r.ЮрАдрес, p.ИНН,r.КПП, p.ОГРН,
		r.Банк,r.БИК, r.Р_счет, r.К_счет, COALESCE(r.Грузополучатель,p.Грузополучатель) ГП,
		COALESCE(r.ОКПО, p.ОКПО) РОКПО	
		INTO rs
		FROM Предприятия p JOIN Реквизиты r ON  p.Код = r.Код 
		WHERE КодРеквизитов = kr; 
			РОКПО:=rs.РОКПО;
			payer:=COALESCE(rs.ЮрНазвание,'')||', '||COALESCE(rs.ЮрАдрес,'');
			IF rs.ИНН IS NOT NULL THEN payer:=payer||E'\n'||'ИНН: '||rs.ИНН; END IF; 
--	
			IF rs.КПП  IS NOT NULL THEN payer:=payer||' КПП: '||rs.КПП; END IF;  
			--IF rs.ОГРН IS NOT NULL THEN payer:=payer||' ОГРН:'||rs.ОГРН; END IF;
			IF rs.Р_счет IS NOT NULL AND rs.Банк IS NOT NULL THEN payer:=payer||E' '||'р/с '||rs.Р_счет||' в '||rs.Банк; END IF;
			IF rs.К_счет IS NOT NULL THEN payer:=payer||', к/с'||rs.К_счет; END IF;
			IF rs.БИК IS NOT NULL THEN payer:=payer||', БИК'||rs.БИК; END IF;
--	
			 РЮрНазвание:=rs.ЮрНазвание;
			 РЮрАдрес:=rs.ЮрАдрес;
			 РИНН:=rs.ИНН;
			 РКПП:=rs.КПП;
--			
	/*РЕКВИЗИТЫ ГРУЗОПОЛУЧАТЕЛЯ*/
	RAISE NOTICE ' kg %',kg;		
	IF kg IS NULL THEN 
--	
	cargo_receiver:=rs.ГП;
	RAISE NOTICE 'Пустой код грузополучателя %', rs.ГП; 
	RAISE NOTICE 'Вместо него: %',rs.ГП;
		IF cargo_receiver IS NULL THEN
--	
			IF rs.ЮрАдрес IS NOT NULL THEN 	cargo_receiver:=rs.ЮрНазвание||' Адрес: '||rs.ЮрАдрес; END IF;
		END IF; 
--	
		IF doc ='Накладная' THEN
--	
		RAISE NOTICE '%',Накладная||' 134 Ок';
			IF rs.ИНН  IS NOT NULL THEN cargo_receiver:=cargo_receiver||' ИНН: '||rs.ИНН; END IF; 
			IF rs.КПП  IS NOT NULL THEN cargo_receiver:=cargo_receiver||' КПП: '||rs.КПП; END IF;  
			IF rs.Р_счет IS NOT NULL AND rs.Банк IS NOT NULL THEN cargo_receiver:=cargo_receiver||' '||'р/с '||rs.Р_счет||' в '||rs.Банк; END IF;
			IF rs.К_счет IS NOT NULL THEN cargo_receiver:=cargo_receiver||', к/с'||rs.К_счет; END IF;
			IF rs.БИК IS NOT NULL THEN cargo_receiver:=cargo_receiver||', БИК'||rs.БИК; END IF;
		RAISE NOTICE '%',cargo_receiver||' Ник';
		END IF; 
ELSE
		SELECT Адрес, ОКПО INTO	cargo_receiver, ГОКПО FROM Грузополучатель WHERE КодГрузополучателя =kg;
	END IF;
END IF;
RAISE NOTICE 'Документ: %',doc||' ';
RAISE NOTICE 'Плательщик: %',payer||' ';
RAISE NOTICE 'Гр/получатель: %',cargo_receiver||' ';
Плательщик:=payer;
Грузополучатель:=cargo_receiver;
--RAISE NOTICE '%',Накладная||' 134 Ок';	
/* ПОДПИСЬ ДОКУМЕНТА*/
--
IF is_gov_holiday(Накладная) THEN 
loc_sign_emp = 226;
ELSE 
loc_sign_emp = usr;
END IF;
--
SELECT p.КодПодписи, p.ЗаДиректора, p.ЗаБухгалтера, p.ВидНомерДатаДокументаБух, p.ВидНомерДатаДокументаДир, p.Должность,
stamp_n_sign
INTO rs
FROM Подписи p WHERE p.КодОтчета::text=doc AND p.КлючФирмы::text=Фирма AND p.НомерСотрудника =loc_sign_emp  
AND p.ДатаСтартаПодписи = 
	(SELECT max(ДатаСтартаПодписи) FROM Подписи  
	WHERE КодОтчета::text=doc AND КлючФирмы::text=Фирма AND НомерСотрудника=loc_sign_emp 
	AND ДатаСтартаПодписи <= Накладная);
--
IF NOT FOUND THEN
SELECT p.КодПодписи, p.ЗаДиректора, p.ЗаБухгалтера, p.ВидНомерДатаДокументаБух, p.ВидНомерДатаДокументаДир, p.Должность,
stamp_n_sign
INTO rs
FROM Подписи p WHERE p.КодОтчета::text=doc AND p.КлючФирмы::text=Фирма AND p.НомерСотрудника =0  
AND p.ДатаСтартаПодписи = 
	(SELECT max(ДатаСтартаПодписи) FROM Подписи  
	WHERE КодОтчета::text=doc AND КлючФирмы::text=Фирма AND НомерСотрудника=0 
	AND ДатаСтартаПодписи <= Накладная);
END IF;
--
RAISE NOTICE 'Основание: %',Основание;
RAISE NOTICE '% ',COALESCE(parent_bill,bill_no);
--
IF Основание IS NULL THEN 
Основание:=trim(coalesce(trim(prefix),'')||
	       CASE WHEN length(COALESCE(parent_bill,bill_no)::text)=8 THEN to_char(COALESCE(parent_bill,bill_no),'0000-0000'::varchar) 
			WHEN length(COALESCE(parent_bill,bill_no)::text)=9 THEN to_char(COALESCE(parent_bill,bill_no),'0000-00000'::varchar) END::text
			||' от '||to_char(COALESCE(parent_date,now()),'dd.mm.yyyy')/*||                 
	'                      '||CASE WHEN Фактура IS NULL OR doc::text ='Счет' OR doc::text ='СчетФакс' /*OR own=91*/ THEN '' ELSE Фактура END*/);
/*	Основание:=trim(coalesce(trim(prefix),'')||to_char(COALESCE(parent_bill,bill_no),'0000-0000')||' от '||to_char(COALESCE(parent_date,now()),'dd.mm.yyyy')||                 
	'                      '||CASE WHEN Фактура IS NULL OR doc::text ='Счет' OR doc::text ='СчетФакс' /*OR own=91*/ THEN '' ELSE Фактура END
			);*/
END IF;		
--
ЗаБухгалтера:=rs.ЗаБухгалтера;
ЗаДиректора:=rs.ЗаДиректора;
ДовЗаБухгалтера:=rs.ВидНомерДатаДокументаБух;
ДовЗаДиректора:=rs.ВидНомерДатаДокументаДир;
Должность:=rs.Должность;
Печать:= rs.stamp_n_sign;
/*Страна:=rs.Республика*/
--
dogovor:= NULL;
/*Получение договора*/
SELECT 'Договор-счет №'::varchar||d.НомерДоговора||' от '||to_char(d.ДатаДоговора,'dd.mm.yyyy')::text 
INTO dogovor
FROM Договор d 
WHERE REPLACE(REPLACE(НомерДоговора,'-',''),' ','')::text  LIKE 'ДС%'||bill_no::text||'%'
AND ВидДоговора=6
;
--
IF NOT FOUND THEN
--

	SELECT 'Договор поставки №'::varchar||d.НомерДоговора||' от '||to_char(d.ДатаДоговора,'dd.mm.yyyy')::text 
	INTO dogovor
	FROM Договор d 
	WHERE REPLACE(REPLACE(НомерДоговора,'-',''),' ','')::text  LIKE '%'||bill_no::text||'%'
	AND ВидДоговора=2;
RAISE NOTICE 'Мы здесь. Счет %, договор', bill_no;
END IF;
--
IF dogovor IS NULL THEN 
	SELECT
	CASE WHEN  d.ВидДоговора=4  THEN 'Договор №' 
	     WHEN d.ВидДоговора=1 OR d.ВидДоговора=2 OR d.ВидДоговора=5 THEN 'Договор поставки №' 
	     WHEN d.ВидДоговора=6 THEN 'Договор-счет №' ELSE 'Договор №' END::varchar||d.НомерДоговора||' от '||to_char(d.ДатаДоговора,'dd.mm.yyyy')::text 
	     INTO dogovor
	FROM (Договор d 
	INNER JOIN ДоговорВиды ON d.ВидДоговора = ДоговорВиды.ВидДоговора) 
	INNER JOIN Счета s0 ON d.КодПредприятия = s0.Код 
	WHERE "№ счета"=bill_no AND ( 
	    (d.ВидДоговора IN (1,4,5) AND date_trunc('year',ДатаДоговора)=date_trunc('Year',current_date)) 
	    OR (d.ВидДоговора=3) OR (d.ВидДоговора <>1 AND s0."Дата счета">=ДатаДоговора) 
	) 
	AND d.ДатаДоговора = (SELECT max(d0.ДатаДоговора) FROM Договор d0 WHERE d0.КодПредприятия=s0.Код AND d0.Фирма::text= s0.фирма); 
END  IF;
/*Добавляем список авансовых счетов-фактур*/
WITH t as (SELECT DISTINCT s.фирма, s.предок Счет, s.Фактура FROM Счета s WHERE предок=bill_no)
SELECT --t.Счет, Ф_БИК , 
STRING_AGG(format('№ %s от %s исправление №- от -',ФактураНаАвансНомер,to_char(ФактураНаАвансДата,'DD.MM.YYYY')),'; ') INTO avans
FROM (SELECT op.Счет, b0.КодЗаписи, КодРеквизитовФирмы,Номер,ДатаПлатежа, Приход, ФактураНаАвансНомер, ФактураНаАвансДата 
	FROM БанкИмпорт b0 JOIN ОплатыНТУ op ON b0.КодЗаписи=op.КодЗаписи AND COALESCE(op.Сумма,0)>0 AND b0.firma::TEXT NOT IN ('АРКОМ','ИПРО')
	WHERE ФактураНаАвансНомер IS NOT NULL ORDER BY ФактураНаАвансДата ASC,ФактураНаАвансНомер ASC) bi 
JOIN t ON bi.Счет=t.Счет
JOIN ФирмаРеквизиты fr ON bi.КодРеквизитовФирмы=fr.КодРеквизитовФирмы
WHERE t.Фактура > bi.ФактураНаАвансДата  AND bi.Счет=t.Счет AND t.фирма <> 'АРКОМ'
GROUP BY t.Счет,fr.Ф_БИК;
/*Перечисление платежей*/
SELECT STRING_AGG(format('%s от %s',t.Номер,to_char(t.ДатаПлатежа,'DD.MM.YYYY')),', ') INTO bill_pp
FROM (SELECT op.Счет, bi.Номер, bi.ДатаПлатежа
FROM ОплатыНТУ op JOIN БанкИмпорт bi ON op.КодЗаписи=bi.КодЗаписи AND op.Счет=bill_no
ORDER BY ДатаПлатежа, Номер) t
GROUP BY t.Счет; 
--
RETURN  QUERY 
	SELECT Фирма, bill_no, 	
	Накладная,Фактура,ФактураДата, АвансФактураДата,ПродавецРекв, 
	ПродавецБанк, Плательщик,Грузополучатель,
	НомерГосКонтракта,ФТелефон, 
	ФОКПО,РОКПО, ГОКПО, 
	ЗаБухгалтера, ЗаДиректора, ДовЗаБухгалтера,ДовЗаДиректора, Должность, СтавкаНДС,
	Основание, 
	ФЮрНазвание, ФЮрАдрес, ФИНН, ФКПП,
	РЮрНазвание,РЮрАдрес,РИНН,РКПП, Префикс, Печать, Страна, dogovor,avans, bill_pp; 
END;
$function$
;

