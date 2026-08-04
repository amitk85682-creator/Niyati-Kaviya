DO $$ 
DECLARE
    rec RECORD;
    v_has_pk boolean;
    v_duplicate_count integer;
    v_has_fks boolean;
    v_fk_names text;
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

    -- 4. Detect duplicates and RAISE EXCEPTION (Fail-fast check)
    SELECT COUNT(*) INTO v_duplicate_count
    FROM (
        SELECT bot_name, user_id
        FROM users 
        GROUP BY bot_name, user_id HAVING COUNT(*) > 1
    ) sub;
    
    IF v_duplicate_count > 0 THEN
        RAISE EXCEPTION 'Migration failed: % duplicate (bot_name, user_id) pairs found. Please resolve manually before migrating to avoid data loss.', v_duplicate_count;
    END IF;

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

    -- 6. Deal with Primary Key and UNIQUE constraints
    SELECT true INTO v_has_pk 
    FROM pg_constraint 
    WHERE conrelid = 'users'::regclass 
      AND contype = 'p'
      AND array_length(conkey, 1) = 1 
      AND conkey[1] = (SELECT attnum FROM pg_attribute WHERE attrelid = 'users'::regclass AND attname = 'user_id');

    IF v_has_pk THEN
        -- Check for foreign key dependencies before replacing user_id PK
        SELECT count(*) > 0, string_agg(conname, ', ') INTO v_has_fks, v_fk_names
        FROM pg_constraint 
        WHERE confrelid = 'users'::regclass;
        
        IF v_has_fks THEN
            RAISE EXCEPTION 'Migration failed: Cannot drop user_id Primary Key because it is referenced by foreign keys: %', v_fk_names;
        END IF;

        -- Safe to replace PK since no dependencies exist
        FOR rec IN 
            SELECT conname 
            FROM pg_constraint 
            WHERE conrelid = 'users'::regclass AND contype = 'p'
        LOOP
            EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || quote_ident(rec.conname);
        END LOOP;
        
        ALTER TABLE users ADD PRIMARY KEY (bot_name, user_id);
    ELSE
        -- If it wasn't the solitary PK (e.g. has a surrogate id), just add a UNIQUE constraint
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint 
            WHERE conrelid = 'users'::regclass 
              AND contype = 'u'
              AND conname = 'users_bot_user_unique'
        ) THEN
            ALTER TABLE users ADD CONSTRAINT users_bot_user_unique UNIQUE (bot_name, user_id);
        END IF;
    END IF;

END $$;
