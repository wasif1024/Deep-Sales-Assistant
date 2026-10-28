---
name: weekly-newsletter
description: "Create the weekly 'This Week in Music' customer newsletter by researching Chinook's top genres in the background and saving the finished HTML. Use when asked to create, write, or send the weekly newsletter or a music-news roundup."
---

# Weekly Newsletter

This runs as a background job. Your part is to start it and later save what
it produces. **newsletter-agent** does all the research and writing.

## 1. Choose the genres

Use the genres Jane names. If she doesn't name any, ask **chinook-analyst**
for the 4 highest-revenue genres across the whole catalogue.

## 2. Start the background job

- Call `start_async_task(subagent_type="newsletter-agent", description=...)`
  **exactly once**, and list the genres in the description, for example
  "Research and write this week's newsletter covering: Rock, Latin, Jazz,
  Classical".
- It returns a task ID straight away. Tell Jane the newsletter is in progress,
  then **end your turn**. Don't poll for status, and don't do any of the
  research yourself.

## 3. When Jane asks if it's ready

1. Call `list_async_tasks()` and take the `task_id` of the newsletter-agent
   entry. Use this rather than an ID you remember from earlier, which may
   have been summarized out of the conversation.
2. Call `check_async_task(task_id)`.
3. Act on the status:
   - **Still running**: give Jane a progress update and stop.
   - **`error`**: tell Jane this week's newsletter couldn't be produced, and
     stop.
   - **`success`**: `result` is the finished HTML. Go straight to step 4 in
     the same turn. Jane already asked for the newsletter, so don't ask her
     again.

## 4. Save it (only once)

- **Check for an existing copy first.** Jane may ask about the same task more
  than once. Run
  `glob("/outputs/newsletter-*-<first 8 chars of task_id>.html")`. If it finds
  a file, tell Jane the newsletter is already saved there, and stop.
- Otherwise, get a timestamp from the code interpreter:
  `new Date().toISOString().slice(0, 19).replace(/:/g, '-')`.
- Use `write_file` to save the HTML **exactly as returned**, with no edits or
  added text, to
  `/outputs/newsletter-<timestamp>-<first 8 chars of task_id>.html`.

## Wrap up

Tell Jane where the newsletter was saved. If the HTML says that any genre was
left out because its research failed, mention that in your own words.
