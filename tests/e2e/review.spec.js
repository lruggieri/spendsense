// Review page (/review): listing, filtering, categorising and editing transactions.
//
// Seed data (see _seed_basic in server.py), all in USD:
//   supermarket  CITY SUPERMARKET          45.20  regexp     -> Groceries
//   metro        METRO CARD TOPUP          20.00  regexp     -> Transport
//   cinema       Cinema Paradiso           15.00  manual     -> Entertainment (source "Manual")
//   bistro       Le Petit Bistro           64.00  manual     -> Restaurants   (group "Summer Trip")
//   bistro2      Le Petit Bistro Downtown  38.00  similarity -> Restaurants
//   taxi_old     TAXI RIDE AIRPORT         52.00  regexp     -> Transport     (group "Summer Trip")
//   market_old   SUPERMARKET EXPRESS       31.00  regexp     -> Groceries

const { test, expect, expectToast, confirmDialog, clickFabAction, txCard } = require('./fixtures');

const filterForm = (page) => page.locator('#filter-form');

async function applyFilters(page, values) {
  const form = filterForm(page);
  for (const [name, value] of Object.entries(values)) {
    const field = form.locator(`[name="${name}"]`);
    if ((await field.evaluate((el) => el.tagName)) === 'SELECT') {
      await field.selectOption(value);
    } else {
      await field.fill(value);
    }
  }
  await form.getByRole('button', { name: 'Apply Filters' }).click();
  await page.waitForLoadState('domcontentloaded');
}

async function pickCategory(page, txId, categoryName) {
  await txCard(page, txId).locator('.category-select-btn').click();
  const modal = page.locator('#category-modal');
  await expect(modal).toHaveClass(/active/);
  await modal.locator(`.modal-category-item[data-category-name="${categoryName}"]`).click();
  await expect(modal).not.toHaveClass(/active/);
}

test.describe('Review page', () => {
  test('lists every transaction with its category and classification source', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await expect(page.locator('.transaction-card')).toHaveCount(7);
    await expect(page.locator('#total-count')).toHaveText('7');
    await expect(page.locator('#total-amount')).toHaveText('$265.20');

    const expectations = [
      [tx.supermarket, 'Groceries', 'REGEXP'],
      [tx.metro, 'Transport', 'REGEXP'],
      [tx.cinema, 'Entertainment', 'MANUAL'],
      [tx.bistro, 'Restaurants', 'MANUAL'],
      [tx.bistro2, 'Restaurants', 'SIMILARITY'],
      [tx.taxi_old, 'Transport', 'REGEXP'],
    ];
    for (const [id, category, source] of expectations) {
      const card = txCard(page, id);
      await expect(card.locator('.badge-category')).toHaveText(category);
      await expect(card.locator('.badge-source')).toHaveText(source);
    }

    // Only similarity-based rows get the "Confirm" and "investigate" affordances.
    await expect(page.locator('.confirm-btn')).toHaveCount(1);
    await expect(txCard(page, tx.bistro2).locator('.confirm-btn')).toBeVisible();
    await expect(page.locator('.investigate-btn')).toHaveCount(1);

    // Newest first by default.
    await expect(page.locator('.transaction-card').first()).toHaveAttribute('data-tx-id', tx.supermarket);
    await expect(page.locator('.transaction-card').last()).toHaveAttribute('data-tx-id', tx.market_old);

    // Group badges are rendered on member transactions.
    await expect(txCard(page, tx.bistro).locator('.group-badge')).toHaveText(/Summer Trip/);
  });

  test('shows an empty state for a user without transactions', async ({ page, login }) => {
    await login();
    await page.goto('/review');
    await expect(page.getByRole('heading', { name: 'No transactions found' })).toBeVisible();
    await expect(page.locator('#total-count')).toHaveText('0');
  });

  test('filters by category including subcategories', async ({ page, seeded }) => {
    await page.goto('/review');
    await applyFilters(page, { category: seeded.ids.categories.Food });

    await expect(page).toHaveURL(new RegExp(`category=${seeded.ids.categories.Food}`));
    await expect(page.locator('.transaction-card')).toHaveCount(4);
    await expect(page.locator('#total-amount')).toHaveText('$178.20');
    await expect(filterForm(page).locator('[name="category"]')).toHaveValue(seeded.ids.categories.Food);

    await applyFilters(page, { category: seeded.ids.categories.Groceries });
    await expect(page.locator('.transaction-card')).toHaveCount(2);

    await filterForm(page).getByRole('link', { name: 'Clear Filters' }).click();
    await expect(page).toHaveURL(/\/review$/);
    await expect(page.locator('.transaction-card')).toHaveCount(7);
  });

  test('filters by classification source and transaction source', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await applyFilters(page, { category_source: 'similarity' });
    await expect(page.locator('.transaction-card')).toHaveCount(1);
    await expect(txCard(page, tx.bistro2)).toBeVisible();

    await applyFilters(page, { category_source: 'manual' });
    await expect(page.locator('.transaction-card')).toHaveCount(2);

    await applyFilters(page, { category_source: 'regexp' });
    await expect(page.locator('.transaction-card')).toHaveCount(4);

    await applyFilters(page, { category_source: '', transaction_source: 'Manual' });
    await expect(page.locator('.transaction-card')).toHaveCount(1);
    await expect(txCard(page, tx.cinema)).toBeVisible();
    await expect(filterForm(page).locator('[name="transaction_source"] option')).toHaveText([
      'All Sources',
      'Manual',
      'Test Bank',
    ]);
  });

  test('filters by date range and sorts by amount', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await applyFilters(page, { sort_by: 'amount' });
    const cards = page.locator('.transaction-card');
    await expect(cards.first()).toHaveAttribute('data-tx-id', tx.bistro);
    await expect(cards.last()).toHaveAttribute('data-tx-id', tx.cinema);

    // Narrow the range to the oldest transaction only.
    const oldest = await txCard(page, tx.market_old).locator('[data-utc-date]').getAttribute('data-utc-date');
    const day = oldest.slice(0, 10);
    await applyFilters(page, { from_date: day, to_date: day, sort_by: 'date' });
    await expect(cards).toHaveCount(1);
    await expect(txCard(page, tx.market_old)).toBeVisible();
    await expect(page.locator('#total-amount')).toHaveText('$31.00');
  });

  test('live search filters cards and recomputes totals @mobile', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    const search = page.locator('#search-input');
    await search.fill('bistro');
    await expect(page.locator('.transaction-card:visible')).toHaveCount(2);
    await expect(page.locator('#total-count')).toHaveText('2');
    await expect(page.locator('#total-amount')).toHaveText('$102.00');
    await expect(page.locator('#filtered-info')).toBeVisible();
    await expect(page.locator('#original-count')).toHaveText('7');
    await expect(txCard(page, tx.supermarket)).toBeHidden();

    await search.fill('');
    await expect(page.locator('.transaction-card:visible')).toHaveCount(7);
    await expect(page.locator('#filtered-info')).toBeHidden();
  });

  test('search query in the URL is applied on load', async ({ page, seeded }) => {
    await page.goto('/review?search=supermarket');
    await expect(page.locator('#search-input')).toHaveValue('supermarket');
    await expect(page.locator('.transaction-card:visible')).toHaveCount(2);
  });

  test('reassigning a category creates a manual assignment @mobile', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await pickCategory(page, tx.metro, 'Entertainment');
    const button = txCard(page, tx.metro).locator('.category-select-btn');
    await expect(button).toHaveClass(/modified/);
    await expect(button.locator('.selected-category-text')).toHaveText('Entertainment');
    await expect(page.locator('#pending-changes-bar')).toHaveClass(/visible/);
    await expect(page.locator('#pending-count')).toHaveText('1');

    await page.locator('#pending-changes-bar').getByRole('button', { name: 'Apply Changes' }).click();
    await expect(page.locator('.flash-success')).toContainText('Successfully reassigned 1 transaction(s).');
    await expect(txCard(page, tx.metro).locator('.badge-category')).toHaveText('Entertainment');
    await expect(txCard(page, tx.metro).locator('.badge-source')).toHaveText('MANUAL');
  });

  test('filters are preserved after applying category changes', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto(`/review?category=${seeded.ids.categories.Transport}`);
    await expect(page.locator('.transaction-card')).toHaveCount(2);

    await pickCategory(page, tx.metro, 'Groceries');
    await page.locator('#pending-changes-bar').getByRole('button', { name: 'Apply Changes' }).click();

    await expect(page).toHaveURL(new RegExp(`category=${seeded.ids.categories.Transport}`));
    await expect(page.locator('.transaction-card')).toHaveCount(1);
  });

  test('pending changes can be cancelled or reverted', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await pickCategory(page, tx.supermarket, 'Transport');
    await pickCategory(page, tx.metro, 'Groceries');
    await expect(page.locator('#pending-count')).toHaveText('2');

    // Picking the original category again drops that change.
    await pickCategory(page, tx.metro, 'Transport');
    await expect(page.locator('#pending-count')).toHaveText('1');

    await page.locator('#pending-changes-bar').getByRole('button', { name: 'Cancel' }).click();
    await expect(page.locator('#pending-changes-bar')).not.toHaveClass(/visible/);
    await expect(txCard(page, tx.supermarket).locator('.selected-category-text')).toHaveText('Groceries');
    await expect(txCard(page, tx.supermarket).locator('.category-select-btn')).not.toHaveClass(/modified/);
  });

  test('closing the category modal without choosing keeps the transaction unchanged', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await txCard(page, tx.supermarket).locator('.category-select-btn').click();
    const modal = page.locator('#category-modal');
    await expect(modal).toHaveClass(/active/);
    // The current category is highlighted, and the clear button is hidden for non-manual rows.
    await expect(modal.locator('.modal-category-item.selected')).toHaveAttribute('data-category-name', 'Groceries');
    await expect(page.locator('#modal-clear-btn')).toBeHidden();
    await modal.locator('.modal-close').click();
    await expect(modal).not.toHaveClass(/active/);
    await expect(page.locator('#pending-changes-bar')).not.toHaveClass(/visible/);
  });

  test('confirming a similarity suggestion turns it into a manual assignment', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    const card = txCard(page, tx.bistro2);
    await card.locator('.confirm-btn').click();
    await expect(card.locator('.confirm-btn')).toBeHidden();
    await expect(page.locator('#pending-count')).toHaveText('1');
    await page.locator('#pending-changes-bar').getByRole('button', { name: 'Apply Changes' }).click();

    await expect(txCard(page, tx.bistro2).locator('.badge-source')).toHaveText('MANUAL');
    await expect(txCard(page, tx.bistro2).locator('.badge-category')).toHaveText('Restaurants');
    await expect(page.locator('.confirm-btn')).toHaveCount(0);
  });

  test('clearing a manual assignment falls back to automatic classification', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await txCard(page, tx.cinema).locator('.category-select-btn').click();
    await page.locator('#modal-clear-btn').click();
    await expect(txCard(page, tx.cinema).locator('.selected-category-text')).toHaveText('Category will be cleared');
    await page.locator('#pending-changes-bar').getByRole('button', { name: 'Apply Changes' }).click();

    await expect(page.locator('.flash-success')).toBeVisible();
    await expect(txCard(page, tx.cinema).locator('.badge-source', { hasText: 'MANUAL' })).toHaveCount(0);
    await expect(page.locator('.badge-source.manual')).toHaveCount(1);
  });

  test('investigating a similarity match lists the closest transactions', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await txCard(page, tx.bistro2).locator('.investigate-btn').click();
    const modal = page.locator('#similarity-modal');
    await expect(modal).toHaveClass(/active/);
    await expect(modal).toContainText('Le Petit Bistro Downtown');
    await expect(modal.locator('.similarity-item').first()).toContainText('Le Petit Bistro');
    await expect(modal.locator('.similarity-score').first()).toHaveText(/\d+\.\d%/);

    await modal.locator('.modal-close').click();
    await expect(modal).not.toHaveClass(/active/);
  });

  test('adds a transaction from the floating action button @mobile', async ({ page, seeded }) => {
    await page.goto('/review');
    await clickFabAction(page, 'Add Transaction');

    const modal = page.locator('#add-transaction-modal');
    await expect(modal).toHaveClass(/active/);
    await expect(modal.locator('.modal-title')).toHaveText('Add New Transaction');
    await expect(page.locator('#add-tx-date')).not.toHaveValue('');

    await page.locator('#add-tx-amount').fill('12.34');
    await page.locator('#add-tx-currency').selectOption('USD');
    await page.locator('#add-tx-description').fill('Farmers market');
    await page.locator('#add-tx-comment').fill('weekly veggies');
    await page.locator('#add-tx-category-btn').click();
    await page.locator('#category-modal .modal-category-item[data-category-name="Groceries"]').click();
    await expect(page.locator('#add-tx-category-text')).toHaveText('Groceries');

    await modal.getByRole('button', { name: 'Add Transaction' }).click();
    await expect(page.locator('#add-tx-message')).toContainText('Transaction added successfully');

    const card = page.locator('.transaction-card', { hasText: 'Farmers market' });
    await expect(card).toBeVisible();
    await expect(card.locator('.badge-category')).toHaveText('Groceries');
    await expect(card.locator('.badge-source')).toHaveText('MANUAL');
    await expect(card.locator('.comment-display')).toHaveText('weekly veggies');
    await expect(card.locator('.info-value[data-amount]')).toContainText('$12.34');
    await expect(page.locator('#total-count')).toHaveText('8');
  });

  test('a new transaction without a category is auto-classified by patterns', async ({ page, seeded }) => {
    await page.goto('/review');
    await clickFabAction(page, 'Add Transaction');
    await page.locator('#add-tx-amount').fill('7');
    await page.locator('#add-tx-currency').selectOption('USD');
    await page.locator('#add-tx-description').fill('NIGHT TAXI HOME');
    await page.locator('#add-transaction-modal').getByRole('button', { name: 'Add Transaction' }).click();

    const card = page.locator('.transaction-card', { hasText: 'NIGHT TAXI HOME' });
    await expect(card.locator('.badge-category')).toHaveText('Transport');
    await expect(card.locator('.badge-source')).toHaveText('REGEXP');
  });

  test('description autocomplete suggests previous manual transactions', async ({ page, seeded }) => {
    await page.goto('/review');
    await clickFabAction(page, 'Add Transaction');
    await page.locator('#add-tx-description').fill('Cine');
    const suggestion = page.locator('#autocomplete-suggestions').getByText('Cinema Paradiso');
    await expect(suggestion).toBeVisible();
    await suggestion.click();
    await expect(page.locator('#add-tx-description')).toHaveValue('Cinema Paradiso');
  });

  test('the add-transaction modal can be dismissed', async ({ page, seeded }) => {
    await page.goto('/review');
    await clickFabAction(page, 'Add Transaction');
    const modal = page.locator('#add-transaction-modal');
    await modal.getByRole('button', { name: 'Cancel' }).click();
    await expect(modal).not.toHaveClass(/active/);
    await expect(page.locator('.transaction-card')).toHaveCount(7);
  });

  test('edits an existing transaction', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await txCard(page, tx.metro).locator('.edit-transaction-btn').click();
    const modal = page.locator('#add-transaction-modal');
    await expect(modal.locator('.modal-title')).toHaveText('Edit Transaction');
    await expect(page.locator('#add-tx-amount')).toHaveValue('20');
    await expect(page.locator('#add-tx-description')).toHaveValue('METRO CARD TOPUP');
    await expect(page.locator('#add-tx-currency')).toHaveValue('USD');
    await expect(page.locator('#add-tx-category-group')).toBeHidden();

    await page.locator('#add-tx-amount').fill('25.50');
    await page.locator('#add-tx-description').fill('METRO MONTHLY PASS');
    await modal.getByRole('button', { name: 'Save Changes' }).click();
    await expect(page.locator('#add-tx-message')).toContainText('Transaction updated successfully');

    const card = txCard(page, tx.metro);
    await expect(card.locator('.info-item').nth(2)).toContainText('METRO MONTHLY PASS');
    await expect(card.locator('.info-value[data-amount]')).toContainText('$25.50');
    await expect(page.locator('#total-amount')).toHaveText('$270.70');
  });

  test('edits and cancels inline comments', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    const section = txCard(page, tx.supermarket).locator('.comment-section');
    await expect(section.locator('.comment-display')).toHaveText('(no comment)');

    await section.locator('.comment-display').click();
    await section.locator('.comment-edit__input').fill('Birthday cake');
    await section.getByRole('button', { name: 'Save' }).click();
    await expectToast(page, 'Comment updated');
    await expect(section.locator('.comment-display')).toHaveText('Birthday cake');

    // Cancel restores the saved value.
    await section.locator('.comment-display').click();
    await section.locator('.comment-edit__input').fill('something else');
    await section.getByRole('button', { name: 'Cancel' }).click();
    await expect(section.locator('.comment-display')).toHaveText('Birthday cake');

    // Persisted, and searchable.
    await page.reload();
    await expect(txCard(page, tx.supermarket).locator('.comment-display')).toHaveText('Birthday cake');
    await page.locator('#search-input').fill('birthday');
    await expect(page.locator('.transaction-card:visible')).toHaveCount(1);
  });

  test('adds and removes a group on a single transaction', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    const card = txCard(page, tx.supermarket);
    await card.getByRole('button', { name: 'Add group' }).click();
    const modal = page.locator('#add-group-modal');
    await expect(modal).toBeVisible();
    await modal.locator('.modal-group-item', { hasText: 'Work' }).click();
    await expectToast(page, 'Group added successfully');
    await expect(card.locator('.group-badge', { hasText: 'Work' })).toBeVisible();

    await page.reload();
    const badge = txCard(page, tx.supermarket).locator('.group-badge', { hasText: 'Work' });
    await expect(badge).toBeVisible();
    await badge.locator('.group-badge-remove').click();
    await confirmDialog(page);
    await expectToast(page, 'Group removed successfully');
    await expect(txCard(page, tx.supermarket).locator('.group-badge')).toHaveCount(0);
  });

  test('clicking a group badge opens that group', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');
    await txCard(page, tx.bistro).locator('.group-badge', { hasText: 'Summer Trip' }).locator('span').click();
    await expect(page).toHaveURL(new RegExp(`/groups\\?group_id=${seeded.ids.groups['Summer Trip']}`));
  });

  test('bulk adds and removes a group on selected transactions', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/review');

    await expect(page.locator('#bulk-actions-bar')).toBeHidden();
    await txCard(page, tx.supermarket).locator('.tx-checkbox').check();
    await txCard(page, tx.metro).locator('.tx-checkbox').check();
    await expect(page.locator('#bulk-actions-bar')).toBeVisible();
    await expect(page.locator('#selected-count')).toHaveText('2 selected');
    expect(await page.locator('#select-all-checkbox').evaluate((el) => el.indeterminate)).toBe(true);

    await page.getByRole('button', { name: '+ Add Group to Selected' }).click();
    await page.locator('#bulk-add-group-modal .modal-group-item', { hasText: 'Work' }).click();
    await expect(page.locator('.group-badge', { hasText: 'Work' })).toHaveCount(2);

    // The page reloads after a bulk action; select one row to bring the bar back.
    await txCard(page, tx.cinema).locator('.tx-checkbox').check();
    await page.locator('#select-all-checkbox').check();
    await expect(page.locator('#selected-count')).toHaveText('7 selected');
    await page.getByRole('button', { name: '- Remove Group from Selected' }).click();
    await page.locator('#bulk-remove-group-modal .modal-group-item', { hasText: 'Work' }).click();
    await confirmDialog(page);
    await expect(page.locator('.group-badge', { hasText: 'Work' })).toHaveCount(0);
    // Other groups are untouched.
    await expect(page.locator('.group-badge', { hasText: 'Summer Trip' })).toHaveCount(2);

    await txCard(page, tx.cinema).locator('.tx-checkbox').check();
    await page.locator('#select-all-checkbox').check();
    await page.locator('#select-all-checkbox').uncheck();
    await expect(page.locator('#bulk-actions-bar')).toBeHidden();
  });

  test('re-categorize all keeps the current filters', async ({ page, seeded }) => {
    await page.goto('/review?category_source=regexp');
    await clickFabAction(page, 'Re-categorize All');
    await expect(page).toHaveURL(/\/review\?category_source=regexp/);
    await expect(page.locator('.transaction-card')).toHaveCount(4);
  });
});
