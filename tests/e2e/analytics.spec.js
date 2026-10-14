// Analytics pages: /charts (current-month breakdown) and /trends (monthly history).
//
// Seeded USD spending: this month Food 147.20 (Groceries 45.20, Restaurants 102.00),
// Transport 20.00, Entertainment 15.00; last month Transport 52.00; two months
// ago Groceries 31.00.

const { test, expect } = require('./fixtures');

/** Click the Chart.js element at (datasetIndex, index) on a canvas. */
async function clickChartPoint(page, canvasId, datasetIndex, index) {
  const point = await page.evaluate(
    ({ canvasId, datasetIndex, index }) => {
      const chart = Chart.getChart(canvasId);
      const el = chart.getDatasetMeta(datasetIndex).data[index];
      const pos = el.tooltipPosition ? el.tooltipPosition() : { x: el.x, y: el.y };
      return { x: pos.x, y: pos.y };
    },
    { canvasId, datasetIndex, index }
  );
  await page.locator(`#${canvasId}`).click({ position: point });
}

const currentMonth = () => new Date().toISOString().slice(0, 7);

test.describe('Charts', () => {
  test('summarises the current month by category', async ({ page, seeded }) => {
    await page.goto('/charts');

    await expect(page.locator('#total-expenses')).toHaveText('$182.20');
    await expect(page.locator('#largest-category')).toHaveText('Food');
    await expect(page.locator('[name="from_date"]')).toHaveValue(`${currentMonth()}-01`);

    const rows = page.locator('#categoryTableBody tr');
    await expect(rows.first()).toContainText('Food');
    await expect(rows.first()).toContainText('$147.20');
    await expect(rows.filter({ hasText: 'Restaurants' })).toContainText('$102.00');
    await expect(rows.filter({ hasText: 'Transport' })).toContainText('$20.00');
    await expect(rows.filter({ hasText: 'Entertainment' })).toContainText('$15.00');

    const pieLabels = await page.evaluate(() => Chart.getChart('pieChart').data.labels);
    expect(pieLabels).toEqual(['Food', 'Transport', 'Entertainment']);
    await expect(page.locator('#barChart')).toBeVisible();
  });

  test('changing the date range recomputes the totals', async ({ page, seeded }) => {
    await page.goto('/charts');
    await page.locator('[name="from_date"]').fill('2000-01-01');
    await page.locator('[name="to_date"]').fill('2100-12-31');
    await page.locator('#charts-filter-form [type="submit"]').click();

    await expect(page).toHaveURL(/from_date=2000-01-01/);
    await expect(page.locator('#total-expenses')).toHaveText('$265.20');
    await expect(page.locator('#categoryTableBody tr').filter({ hasText: 'Transport' })).toContainText('$72.00');
  });

  test('clicking a table row drills down into the review page', async ({ page, seeded }) => {
    await page.goto('/charts');
    await page.locator('#categoryTableBody tr', { hasText: 'Groceries' }).click();

    await expect(page).toHaveURL(new RegExp(`/review\\?category=${seeded.ids.categories.Groceries}&from_date=`));
    await expect(page.locator('.transaction-card')).toHaveCount(1);
    await expect(page.locator('.transaction-card')).toContainText('CITY SUPERMARKET');
  });

  test('clicking a pie slice drills down into the review page', async ({ page, seeded }) => {
    await page.goto('/charts');
    // Slice 0 is the largest category: Food (including its subcategories).
    await clickChartPoint(page, 'pieChart', 0, 0);
    await expect(page).toHaveURL(new RegExp(`category=${seeded.ids.categories.Food}`));
    await expect(page.locator('.transaction-card')).toHaveCount(3);
  });

  test('handles a user without any data', async ({ page, login }) => {
    await login();
    await page.goto('/charts');
    await expect(page.locator('#total-expenses')).toHaveText('$0.00');
    await expect(page.locator('#largest-category')).toHaveText('-');
    await expect(page.locator('#categoryTableBody tr')).toHaveCount(0);
  });
});

test.describe('Trends', () => {
  test('summarises monthly spending', async ({ page, seeded }) => {
    await page.goto('/trends');

    await expect(page.locator('#total-months')).toHaveText('3');
    await expect(page.locator('#avg-monthly')).toHaveText('$88');
    await expect(page.locator('#highest-month')).toHaveText(currentMonth());

    const summary = await page.evaluate(() => {
      const chart = Chart.getChart('summaryChart');
      return { labels: chart.data.labels, totals: chart.data.datasets[0].data };
    });
    expect(summary.labels).toHaveLength(3);
    expect(summary.labels[2]).toBe(currentMonth());
    expect(summary.totals.map(Number)).toEqual([31, 52, 182.2]);
  });

  test('category buttons isolate and restore chart lines', async ({ page, seeded }) => {
    await page.goto('/trends');

    const visibleLabels = () =>
      page.evaluate(() => {
        const chart = Chart.getChart('trendsChart');
        return chart.data.datasets.filter((_, i) => chart.isDatasetVisible(i)).map((d) => d.label);
      });

    const allLabels = await visibleLabels();
    expect(allLabels).toEqual(expect.arrayContaining(['Food', 'Groceries', 'Restaurants', 'Transport']));

    await page.locator('#categoryButtons').getByRole('button', { name: 'Show Food' }).click();
    await expect.poll(visibleLabels).toEqual(expect.arrayContaining(['Food', 'Groceries', 'Restaurants']));
    expect(await visibleLabels()).not.toContain('Transport');

    await page.getByRole('button', { name: 'Hide All Categories' }).first().click();
    await expect.poll(visibleLabels).toEqual([]);

    await page.getByRole('button', { name: 'Show All Categories' }).first().click();
    await expect.poll(visibleLabels).toEqual(allLabels);
  });

  test('fetcher usage can switch between amount and count', async ({ page, seeded }) => {
    await page.goto('/trends');

    const fetcherData = () =>
      page.evaluate(() => {
        const chart = Chart.getChart('fetcherUsageChart');
        return chart.data.datasets.map((d) => ({ label: d.label, data: d.data.map(Number) }));
      });

    const amounts = await fetcherData();
    const testBank = amounts.find((d) => d.label.includes('Test Bank'));
    expect(testBank.data.reduce((a, b) => a + b, 0)).toBeCloseTo(250.2, 1);

    await page.locator('#fetcherUsageToggle').getByRole('button', { name: 'Count' }).click();
    await expect(page.locator('#fetcherUsageToggle [data-mode="count"]')).not.toHaveClass(/secondary/);
    const counts = (await fetcherData()).find((d) => d.label.includes('Test Bank'));
    expect(counts.data.reduce((a, b) => a + b, 0)).toBe(6);

    await page.locator('#fetcherHideAll').click();
    expect(
      await page.evaluate(() => {
        const chart = Chart.getChart('fetcherUsageChart');
        return chart.data.datasets.some((_, i) => chart.isDatasetVisible(i));
      })
    ).toBe(false);
    await page.locator('#fetcherShowAll').click();
    expect(
      await page.evaluate(() => {
        const chart = Chart.getChart('fetcherUsageChart');
        return chart.data.datasets.every((_, i) => chart.isDatasetVisible(i));
      })
    ).toBe(true);
  });

  test('clicking a data point opens that month and category in review', async ({ page, seeded }) => {
    await page.goto('/trends');
    const { datasetIndex, index } = await page.evaluate(() => {
      const chart = Chart.getChart('trendsChart');
      return {
        datasetIndex: chart.data.datasets.findIndex((d) => d.label === 'Transport'),
        index: chart.data.labels.length - 1,
      };
    });
    // Isolate the line so no other point is closer to the click.
    await page.locator('#categoryButtons').getByRole('button', { name: 'Show Transport' }).click();
    await clickChartPoint(page, 'trendsChart', datasetIndex, index);

    await expect(page).toHaveURL(new RegExp(`/review\\?from_date=.*category=${seeded.ids.categories.Transport}`));
    await expect(page.locator('.transaction-card')).toHaveCount(1);
    await expect(page.locator('.transaction-card')).toContainText('METRO CARD TOPUP');
  });
});
