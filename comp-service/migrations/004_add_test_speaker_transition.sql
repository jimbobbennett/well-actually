INSERT INTO public.speech_log_test (time, sid, content, ms_score)
VALUES
    (TIMESTAMP '2026-10-22T09:59:30', 1, 'The webhook bug came from accepting unchecked JSON. I already understand TypeScript interfaces and narrowing; the missing piece is runtime validation of the external payload before we use it.', 0),
    (TIMESTAMP '2026-10-22T10:00:00', 3, 'Let’s focus on the implementation. Maya, walk us through the validation boundary and how you want to handle the amount field.', 0),
    (TIMESTAMP '2026-10-22T10:00:30', 1, 'I’ll receive the payload as unknown, validate the object structure, and check that amount is a finite number within the allowed range. An interface alone won’t validate JSON arriving over the network.', 0),
    (TIMESTAMP '2026-10-22T10:01:00', 1, 'After validation, the parser will return a typed result. A discriminated union will separate successful parsing from validation failure, so callers must handle both cases before accessing payment fields.', 0),
    (TIMESTAMP '2026-10-22T10:01:30', 1, 'I’ve already implemented the parser and tests for strings, missing fields, NaN, and invalid amounts. What I need feedback on is whether the webhook should reject invalid messages or send them to a retry queue.', 0),
    (TIMESTAMP '2026-10-22T10:02:00', 2, 'Before we get ahead of ourselves, let me simplify this for you. TypeScript interfaces are like labels on boxes: they tell you what belongs inside. But JSON comes from outside, so you have to check it at runtime. Unknown means you need to inspect the value first, and a discriminated union makes you handle different outcomes. Once you understand those basics, we can talk about your parser.', 0)
ON CONFLICT (time) DO NOTHING;
