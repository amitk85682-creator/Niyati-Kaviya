DO $$ 
DECLARE
    rec RECORD;
    v_constraint_name text;
    v_has_pk boolean;
BEGIN
    -- 1. Add bot_name column if missing
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'bot_name'
    ) THEN
        ALTER TABLE users ADD COLUMN bot_name text;
    END IF;

    -- 2. Backfill existing rows with 'niyati'
    UPDATE users SET bot_name = 'niyati' WHERE bot_name IS NULL;

    -- 3. Set bot_name to NOT NULL
    ALTER TABLE users ALTER COLUMN bot_name SET NOT NULL;
    ALTER TABLE users ALTER COLUMN bot_name SET DEFAULT 'niyati';

    -- 4. Safely deduplicate if multiple (bot_name, user_id) pairs exist before constraint
    -- We keep the most recently updated one and delete older duplicates
    DELETE FROM users a USING (
      SELECT MIN(ctid) as ctid, bot_name, user_id
        FROM users 
        GROUP BY bot_name, user_id HAVING COUNT(*) > 1
    ) b
    WHERE a.bot_name = b.bot_name 
      AND a.user_id = b.user_id 
      AND a.ctid <> b.ctid;

    -- 5. Detect and remove ONLY user_id-only UNIQUE constraints
    FOR rec IN 
        SELECT conname 
        FROM pg_constraint 
        WHERE conrelid = 'users'::regclass 
          AND contype = 'u' 
          AND array_length(conkey, 1) = 1 
          AND conkey[1] = (SELECT attnum FROM pg_attribute WHERE attrelid = 'users'::regclass AND attname = 'user_id')
    LOOP
        EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || quote_ident(rec.conname);
    END LOOP;

    -- 6. Add UNIQUE constraint for (bot_name, user_id)
    -- A UNIQUE constraint automatically creates a backing index, so no duplicate CREATE INDEX is needed.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'users'::regclass 
          AND contype = 'u'
          AND conname = 'users_bot_user_unique'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_bot_user_unique UNIQUE (bot_name, user_id);
    END IF;

    -- 7. Deal with Primary Key ONLY if user_id is the solitary PK.
    -- If there's a surrogate 'id' PK, preserve it untouched.
    SELECT true INTO v_has_pk 
    FROM pg_constraint 
    WHERE conrelid = 'users'::regclass 
      AND contype = 'p'
      AND array_length(conkey, 1) = 1 
      AND conkey[1] = (SELECT attnum FROM pg_attribute WHERE attrelid = 'users'::regclass AND attname = 'user_id');

    IF v_has_pk THEN
        -- If user_id is the only PK, we must drop it and make (bot_name, user_id) the PK.
        -- We will not use CASCADE. If foreign keys exist, they must be handled manually, 
        -- but for this bot 'users' is typically a leaf table.
        FOR rec IN 
            SELECT conname 
            FROM pg_constraint 
            WHERE conrelid = 'users'::regclass AND contype = 'p'
        LOOP
            EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || quote_ident(rec.conname);
        END LOOP;
        
        ALTER TABLE users ADD PRIMARY KEY (bot_name, user_id);
    END IF;

END $$;
