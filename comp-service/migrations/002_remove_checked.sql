-- Removes only processing flags; preserves speech content and scores.
ALTER TABLE public.speech_log DROP COLUMN IF EXISTS checked;
