---
name: territory-report
description: "Produce a sales report on Jane's accounts (revenue, top customers, genre mix, trends) with a chart. Use when asked for a territory report, a sales summary, performance numbers, or 'how are my accounts doing'."
---

# Territory Report

All the figures come from the database. The chart is drawn from those same
figures.

## 1. Collect the numbers

Ask **chinook-analyst** for the following, limited to Jane's customers
(`SupportRepId = 3`):
- total revenue and number of invoices
- top customers by revenue, with amounts
- revenue broken down by genre
- a trend if one is useful, such as revenue by year

If you need to combine results, do the math with the **code interpreter**.

## 2. Write the report

- Get a timestamp from the code interpreter:
  `new Date().toISOString().slice(0, 19).replace(/:/g, '-')`.
  Including the time, not just the date, means a second report on the same
  day gets its own file.
- Use `write_file` to save a Markdown report to
  `/outputs/territory_report-<timestamp>.md`. It should contain the headline
  totals, a list of top customers, and a revenue-by-genre table.

## 3. Draw the chart

- Use `write_file` to create a short Python script that draws revenue by
  genre as a matplotlib pie chart and saves it to
  `/outputs/territory_chart-<timestamp>.png` (same timestamp as the report).
- Run the script with `execute`, installing matplotlib first if it's missing.
- **In the report file**, refer to the image by its bare filename:
  `![Revenue by Genre](territory_chart-<timestamp>.png)`. When Jane downloads
  them, the report and the chart end up side by side in the same folder, so
  only a relative path will work.

## Wrap up

- Tell Jane where the report and chart were saved, and give her the headline
  revenue figure.
- **In your chat reply**, show the chart inline using the full absolute path:
  `![Revenue by Genre](/outputs/territory_chart-<timestamp>.png)`. The chat
  needs the absolute path to display the image instead of just a download
  link.
