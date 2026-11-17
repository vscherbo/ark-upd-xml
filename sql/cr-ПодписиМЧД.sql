-- arc_energo."ПодписиМЧД" определение

-- Drop table

-- DROP TABLE arc_energo."ПодписиМЧД";

CREATE TABLE arc_energo."ПодписиМЧД" (
    "НомДовер" uuid NOT NULL,
    "ДатаВыдДовер" date NULL, -- в УПД нужен ДД.ММ.ГГГГ
    "ВнНомДовер" varchar NULL, -- Внутренний номер из ИС доверителя
    "ДатаВнРегДовер" date NULL, -- Дата регистрации в системе хранения
    "СведСист" varchar NULL, -- ссылка вида https://m4d.nalog.gov.ru/EMCHD/check-status?guid=<GUID>
    "ИдСистХран" varchar NULL, -- Идентификатор вашей системы хранения
    CONSTRAINT подписимчд_pk PRIMARY KEY ("НомДовер")
);

-- Column comments

COMMENT ON COLUMN arc_energo."ПодписиМЧД"."ДатаВыдДовер" IS 'в УПД нужен ДД.ММ.ГГГГ';
COMMENT ON COLUMN arc_energo."ПодписиМЧД"."ВнНомДовер" IS 'Внутренний номер из ИС доверителя';
COMMENT ON COLUMN arc_energo."ПодписиМЧД"."ДатаВнРегДовер" IS 'Дата регистрации в системе хранения';
COMMENT ON COLUMN arc_energo."ПодписиМЧД"."СведСист" IS 'ссылка вида https://m4d.nalog.gov.ru/EMCHD/check-status?guid=<GUID>';
COMMENT ON COLUMN arc_energo."ПодписиМЧД"."ИдСистХран" IS 'Идентификатор вашей системы хранения';

-- Permissions

ALTER TABLE arc_energo."ПодписиМЧД" OWNER TO arc_energo;
GRANT ALL ON TABLE arc_energo."ПодписиМЧД" TO arc_energo;
