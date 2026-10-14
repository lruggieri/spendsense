// Transaction groups (/groups).

const { test, expect, expectToast, confirmDialog, clickFabAction, txCard } = require('./fixtures');

const groupCard = (page, name) =>
  page.locator('.group-card', { has: page.locator('.group-name', { hasText: new RegExp(`^${name}$`) }) });

test.describe('Groups', () => {
  test('lists groups with their transaction counts', async ({ page, seeded }) => {
    await page.goto('/groups');
    await expect(page.locator('.group-card')).toHaveCount(2);
    await expect(groupCard(page, 'Summer Trip').locator('.stat-value')).toHaveText('2');
    await expect(groupCard(page, 'Work').locator('.stat-value')).toHaveText('0');
    await expect(page.locator('.transactions-section')).toHaveCount(0);
  });

  test('shows an empty state and creates the first group @mobile', async ({ page, login }) => {
    await login();
    await page.goto('/groups');
    await expect(page.getByRole('heading', { name: 'No groups yet' })).toBeVisible();

    await page.getByRole('button', { name: '+ Create Group' }).click();
    await page.locator('#create-group-name').fill('Groceries 2026');
    await page.locator('#create-group-modal').getByRole('button', { name: 'Create Group' }).click();
    await expect(groupCard(page, 'Groceries 2026')).toBeVisible();
  });

  test('creates a group from the floating action button', async ({ page, seeded }) => {
    await page.goto('/groups');
    await clickFabAction(page, 'Create Group');
    const modal = page.locator('#create-group-modal');
    await expect(modal).toBeVisible();
    await expect(page.locator('#create-group-name')).toBeFocused();
    await page.locator('#create-group-name').fill('Home Renovation');
    await modal.getByRole('button', { name: 'Create Group' }).click();
    await expect(groupCard(page, 'Home Renovation')).toBeVisible();
    await expect(page.locator('.group-card')).toHaveCount(3);
  });

  test('cancelling group creation keeps the list unchanged', async ({ page, seeded }) => {
    await page.goto('/groups');
    await clickFabAction(page, 'Create Group');
    await page.locator('#create-group-name').fill('Nope');
    await page.locator('#create-group-modal').getByRole('button', { name: 'Cancel' }).click();
    await expect(page.locator('#create-group-modal')).toBeHidden();
    await expect(page.locator('.group-card')).toHaveCount(2);
  });

  test('renames a group', async ({ page, seeded }) => {
    await page.goto('/groups');
    await groupCard(page, 'Work').getByTitle('Edit group').click();
    const modal = page.locator('#edit-group-modal');
    await expect(modal).toBeVisible();
    await expect(page.locator('#edit-group-name')).toHaveValue('Work');
    await page.locator('#edit-group-name').fill('Business');
    await modal.getByRole('button', { name: 'Update Group' }).click();
    await expect(groupCard(page, 'Business')).toBeVisible();
    await expect(groupCard(page, 'Work')).toHaveCount(0);
  });

  test('deletes a group and detaches it from its transactions', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/groups');

    await groupCard(page, 'Summer Trip').getByTitle('Delete group').click();
    const modal = page.locator('#delete-group-modal');
    await expect(modal).toBeVisible();
    await expect(page.locator('#delete-group-name-display')).toHaveText('Summer Trip');
    await expect(page.locator('#delete-group-warning')).toContainText('assigned to 2 transaction(s)');

    // Cancel first, then really delete.
    await modal.getByRole('button', { name: 'Cancel' }).click();
    await expect(modal).toBeHidden();
    await groupCard(page, 'Summer Trip').getByTitle('Delete group').click();
    await modal.getByRole('button', { name: 'Delete Group' }).click();

    await expect(page).toHaveURL(/\/groups$/);
    await expect(groupCard(page, 'Summer Trip')).toHaveCount(0);

    await page.goto('/review');
    await expect(txCard(page, tx.bistro).locator('.group-badge')).toHaveCount(0);
  });

  test('empty groups explain how to add transactions', async ({ page, seeded }) => {
    await page.goto('/groups');
    await groupCard(page, 'Work').getByRole('button', { name: 'View Transactions' }).click();
    await expect(page).toHaveURL(new RegExp(`group_id=${seeded.ids.groups.Work}`));
    await expect(page.getByRole('heading', { name: 'No transactions in this group' })).toBeVisible();
  });

  test('views a group with its transactions, totals and chart', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/groups');
    await groupCard(page, 'Summer Trip').getByRole('button', { name: 'View Transactions' }).click();

    await expect(page).toHaveURL(new RegExp(`group_id=${seeded.ids.groups['Summer Trip']}`));
    await expect(page.getByRole('heading', { name: /Transactions in "Summer Trip"/ })).toBeVisible();
    await expect(page.locator('.transaction-card')).toHaveCount(2);
    await expect(txCard(page, tx.bistro)).toBeVisible();
    await expect(txCard(page, tx.taxi_old)).toBeVisible();
    await expect(page.locator('#total-count')).toHaveText('2');
    await expect(page.locator('#total-amount')).toHaveText('$116.00');

    // The category breakdown chart is rendered with one bar per top-level category.
    await expect(page.locator('#groupBarChart')).toBeVisible();
    const labels = await page.evaluate(() => Chart.getChart('groupBarChart').data.labels);
    expect(labels).toEqual(expect.arrayContaining(['Food', 'Transport']));

    await page.getByRole('link', { name: 'Clear Filter', exact: true }).click();
    await expect(page).toHaveURL(/\/groups$/);
    await expect(page.locator('.transactions-section')).toHaveCount(0);
  });

  test('searches and sorts within a group', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto(`/groups?group_id=${seeded.ids.groups['Summer Trip']}`);

    await page.locator('#search-input').fill('taxi');
    await expect(page.locator('.transaction-card:visible')).toHaveCount(1);
    await expect(page.locator('#total-amount')).toHaveText('$52.00');
    await page.locator('#search-input').fill('');

    await page.locator('.filter-form [name="sort_by"]').selectOption('amount');
    await page.locator('.filter-form [type="submit"]').click();
    await expect(page).toHaveURL(/sort_by=amount/);
    await expect(page.locator('.transaction-card').first()).toHaveAttribute('data-tx-id', tx.bistro);
  });

  test('recategorizes a transaction from inside a group', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    const groupId = seeded.ids.groups['Summer Trip'];
    await page.goto(`/groups?group_id=${groupId}`);

    await txCard(page, tx.taxi_old).locator('.category-select-btn').click();
    await page.locator('#category-modal .modal-category-item[data-category-name="Entertainment"]').click();
    await page.locator('#pending-changes-bar').getByRole('button', { name: 'Apply Changes' }).click();

    // Stays on the same group page after saving.
    await expect(page).toHaveURL(new RegExp(`/groups\\?group_id=${groupId}`));
    await expect(txCard(page, tx.taxi_old).locator('.badge-category')).toHaveText('Entertainment');
    await expect(txCard(page, tx.taxi_old).locator('.badge-source')).toHaveText('MANUAL');
  });

  test('removes a transaction from the group it is viewed in', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto(`/groups?group_id=${seeded.ids.groups['Summer Trip']}`);
    await txCard(page, tx.taxi_old).locator('.group-badge-remove').click();
    await confirmDialog(page);
    await expectToast(page, 'Group removed successfully');
    await page.reload();
    await expect(page.locator('.transaction-card')).toHaveCount(1);
  });
});
