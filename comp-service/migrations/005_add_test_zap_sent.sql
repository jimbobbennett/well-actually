ALTER TABLE public.speech_log_test
    ADD COLUMN IF NOT EXISTS zap_sent BOOLEAN;
