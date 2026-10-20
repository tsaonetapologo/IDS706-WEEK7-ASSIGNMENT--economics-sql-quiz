-- Run once in the Supabase SQL Editor for the project used by this app.
CREATE TABLE IF NOT EXISTS public.economic_indicators (
    country text NOT NULL,
    year integer NOT NULL DEFAULT 2024,
    gdp_per_capita numeric NOT NULL,
    inflation_rate numeric NOT NULL,
    unemployment_rate numeric NOT NULL,
    population bigint NOT NULL
);

-- Also update an existing table, since CREATE TABLE IF NOT EXISTS does not
-- change defaults on columns created before this setup script was updated.
ALTER TABLE public.economic_indicators
    ALTER COLUMN year SET DEFAULT 2024;
UPDATE public.economic_indicators
SET year = 2024
WHERE year IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS economic_indicators_country_quiz_uidx
    ON public.economic_indicators (country);

INSERT INTO public.economic_indicators (
    country,
    year,
    gdp_per_capita,
    inflation_rate,
    unemployment_rate,
    population
)
VALUES
    ('Botswana', 2024, 7200, 3.2, 25.9, 2630000),
    ('Ghana', 2024, 2400, 22.8, 14.7, 34100000),
    ('Kenya', 2024, 2200, 4.5, 5.7, 56400000),
    ('Mauritius', 2024, 12500, 4.0, 6.0, 1260000),
    ('Namibia', 2024, 4800, 4.2, 19.4, 3030000),
    ('Nigeria', 2024, 1600, 24.5, 5.0, 232000000),
    ('Rwanda', 2024, 1100, 4.8, 14.9, 14000000),
    ('South Africa', 2024, 6500, 4.4, 32.5, 64000000),
    ('Uganda', 2024, 1100, 3.3, 9.0, 50000000),
    ('Zambia', 2024, 1300, 15.0, 13.0, 21300000)
ON CONFLICT (country) DO UPDATE SET
    year = EXCLUDED.year,
    gdp_per_capita = EXCLUDED.gdp_per_capita,
    inflation_rate = EXCLUDED.inflation_rate,
    unemployment_rate = EXCLUDED.unemployment_rate,
    population = EXCLUDED.population;

DO $$
BEGIN
    CREATE ROLE quiz_reader NOLOGIN;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

GRANT quiz_reader TO postgres;
GRANT USAGE ON SCHEMA public TO quiz_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM quiz_reader;
GRANT SELECT ON public.economic_indicators TO quiz_reader;

ALTER TABLE public.economic_indicators ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS economic_indicators_quiz_read
    ON public.economic_indicators;
CREATE POLICY economic_indicators_quiz_read
    ON public.economic_indicators
    FOR SELECT
    TO anon, authenticated, quiz_reader
    USING (true);

CREATE TABLE IF NOT EXISTS public.quiz_saves (
    user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    question_number smallint NOT NULL CHECK (question_number BETWEEN 1 AND 5),
    sql_text text NOT NULL CHECK (length(sql_text) <= 10000),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, question_number)
);

ALTER TABLE public.quiz_saves ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS quiz_saves_owner_access ON public.quiz_saves;
CREATE POLICY quiz_saves_owner_access
    ON public.quiz_saves
    FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.quiz_saves
    TO authenticated;
