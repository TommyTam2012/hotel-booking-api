-- SQLite schema for BCM Demo Agent FAQ

-- Table to store structured FAQ/intents for quick retrieval
CREATE TABLE faq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent TEXT NOT NULL,         -- Short name for the intent (e.g., 'course_duration')
    question TEXT NOT NULL,       -- Example user question
    answer TEXT NOT NULL          -- Short, precise answer
);

-- Seed data: common intents for BCM demo
INSERT INTO faq (intent, question, answer) VALUES
('course_duration', 'How long is the GI program?', 'Our flagship GI™ program runs for 6 weeks, with 12 months of mentorship for long-term results.'),
('fees', 'How much does it cost?', 'Investment varies by package. Let’s arrange a quick consultation to find the best fit for you.'),
('start_dates', 'When does the next course start?', 'New cohorts start regularly; the next intake opens soon.'),
('class_size', 'How many students per class?', 'We work in small groups to ensure personal attention, combined with 1-on-1 checkpoints to keep you on track.'),
('general', 'What is BCM?', 'BCM helps entrepreneurs grow global revenue with proven systems, serving over 40,000 people in 30+ countries.');
-- Enrollments table (portable to Postgres later)
CREATE TABLE IF NOT EXISTS enrollments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  program_code TEXT,        -- e.g., 'GI' or 'SPP'
  cohort_code TEXT,         -- optional (e.g., 'GI-2025-03')
  timezone TEXT,            -- e.g., 'Asia/Hong_Kong'
  notes TEXT,               -- free text from user
  source TEXT,              -- 'avatar', 'form', 'agent', etc.
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helpful index for lookups (optional)
CREATE INDEX IF NOT EXISTS idx_enrollments_created_at 
ON enrollments (created_at DESC);
