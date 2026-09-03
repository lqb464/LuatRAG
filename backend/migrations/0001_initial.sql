CREATE TABLE `audit_events` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`action` text NOT NULL,
	`resource_type` text NOT NULL,
	`resource_id` text,
	`metadata_json` text,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_audit_owner_created` ON `audit_events` (`owner_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `chunks` (
	`id` text PRIMARY KEY NOT NULL,
	`source_id` text NOT NULL,
	`owner_id` text NOT NULL,
	`ordinal` integer NOT NULL,
	`locator` text NOT NULL,
	`heading` text,
	`text` text NOT NULL,
	`text_folded` text NOT NULL,
	`checksum` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`source_id`) REFERENCES `sources`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_chunks_owner_source` ON `chunks` (`owner_id`,`source_id`);--> statement-breakpoint
CREATE INDEX `idx_chunks_source_ordinal` ON `chunks` (`source_id`,`ordinal`);--> statement-breakpoint
CREATE TABLE `conversations` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`title` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_conversations_owner_updated` ON `conversations` (`owner_id`,`updated_at`);--> statement-breakpoint
CREATE TABLE `messages` (
	`id` text PRIMARY KEY NOT NULL,
	`conversation_id` text NOT NULL,
	`owner_id` text NOT NULL,
	`role` text NOT NULL,
	`content` text NOT NULL,
	`evidence_json` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_messages_conversation_created` ON `messages` (`conversation_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `query_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`conversation_id` text,
	`question_hash` text NOT NULL,
	`model` text NOT NULL,
	`retrieved_count` integer NOT NULL,
	`citation_count` integer NOT NULL,
	`insufficient_context` integer DEFAULT false NOT NULL,
	`duration_ms` integer NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_query_runs_owner_created` ON `query_runs` (`owner_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `rate_limits` (
	`key` text PRIMARY KEY NOT NULL,
	`count` integer DEFAULT 0 NOT NULL,
	`expires_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `sources` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`name` text NOT NULL,
	`kind` text NOT NULL,
	`mime_type` text NOT NULL,
	`byte_size` integer NOT NULL,
	`sha256` text NOT NULL,
	`source_url` text,
	`r2_key` text,
	`extracted_key` text,
	`status` text DEFAULT 'ready' NOT NULL,
	`chunk_count` integer DEFAULT 0 NOT NULL,
	`error_code` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_sources_owner_created` ON `sources` (`owner_id`,`created_at`);
--> statement-breakpoint
CREATE VIRTUAL TABLE `chunks_fts` USING fts5(
	`chunk_id` UNINDEXED,
	`owner_id` UNINDEXED,
	`source_id` UNINDEXED,
	`title`,
	`text`,
	`text_folded`,
	tokenize='unicode61 remove_diacritics 2'
);
--> statement-breakpoint
CREATE TRIGGER `chunks_fts_after_insert` AFTER INSERT ON `chunks` BEGIN
	INSERT INTO `chunks_fts` (`chunk_id`, `owner_id`, `source_id`, `title`, `text`, `text_folded`)
	VALUES (
		new.`id`,
		new.`owner_id`,
		new.`source_id`,
		COALESCE((SELECT `name` FROM `sources` WHERE `id` = new.`source_id`), '') || ' ' || COALESCE(new.`heading`, ''),
		new.`text`,
		new.`text_folded`
	);
END;
--> statement-breakpoint
CREATE TRIGGER `chunks_fts_after_delete` AFTER DELETE ON `chunks` BEGIN
	DELETE FROM `chunks_fts` WHERE `chunk_id` = old.`id`;
END;
--> statement-breakpoint
CREATE TRIGGER `chunks_fts_after_update` AFTER UPDATE ON `chunks` BEGIN
	DELETE FROM `chunks_fts` WHERE `chunk_id` = old.`id`;
	INSERT INTO `chunks_fts` (`chunk_id`, `owner_id`, `source_id`, `title`, `text`, `text_folded`)
	VALUES (
		new.`id`,
		new.`owner_id`,
		new.`source_id`,
		COALESCE((SELECT `name` FROM `sources` WHERE `id` = new.`source_id`), '') || ' ' || COALESCE(new.`heading`, ''),
		new.`text`,
		new.`text_folded`
	);
END;
--> statement-breakpoint
PRAGMA optimize;
