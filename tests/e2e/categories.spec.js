// Category management (/categories).

const { test, expect, expectToast, confirmDialog, clickFabAction, clickAndWaitForReload } = require('./fixtures');

const row = (page, name) =>
  page.locator('.category-table tbody tr', { has: page.locator('.category-name', { hasText: new RegExp(`^${name}$`) }) });

test.describe('Categories', () => {
  test('shows the category tree with system categories protected', async ({ page, seeded }) => {
    await page.goto('/categories');

    const names = page.locator('.category-table tbody .category-name');
    await expect(names).toContainText(['Food', 'Groceries', 'Restaurants', 'Transport', 'Entertainment', 'Unknown']);
    // Children are indented under their parent.
    await expect(row(page, 'Groceries').locator('.tree-icon')).toBeVisible();
    await expect(row(page, 'Food').locator('.tree-icon')).toHaveCount(0);
    await expect(row(page, 'Food').locator('.category-description')).toHaveText('Food expenses');

    const unknown = row(page, 'Unknown');
    await expect(unknown.locator('.badge-system')).toHaveText('System');
    await expect(unknown.locator('button')).toHaveCount(0);
  });

  test('creates root and child categories @mobile', async ({ page, seeded }) => {
    await page.goto('/categories');

    await clickFabAction(page, 'Create Category');
    const modal = page.locator('#category-modal');
    await expect(modal).toBeVisible();
    await expect(modal.locator('#modal-title')).toHaveText('Create Category');
    await page.locator('#category-name').fill('Health');
    await page.locator('#category-description').fill('Doctors and pharmacy');
    await clickAndWaitForReload(page, modal.getByRole('button', { name: 'Save' }));
    await expect(row(page, 'Health')).toBeVisible();
    await expect(row(page, 'Health').locator('.category-description')).toHaveText('Doctors and pharmacy');

    await clickFabAction(page, 'Create Category');
    await page.locator('#category-name').fill('Pharmacy');
    await page.locator('#category-parent').selectOption({ label: 'Health' });
    await modal.getByRole('button', { name: 'Save' }).click();
    await expect(row(page, 'Pharmacy')).toBeVisible();
    await expect(row(page, 'Pharmacy').locator('.tree-icon')).toBeVisible();

    // New categories are immediately available on the review page.
    await page.goto('/review');
    await expect(page.locator('#filter-form [name="category"] option', { hasText: 'Pharmacy' })).toHaveCount(1);
  });

  test('validates the category name', async ({ page, seeded }) => {
    await page.goto('/categories');
    await clickFabAction(page, 'Create Category');
    await page.locator('#category-modal').getByRole('button', { name: 'Save' }).click();
    await expectToast(page, 'Category Name is required');
    await expect(page.locator('#category-name')).toHaveAttribute('maxlength', '40');
  });

  test('cancelling the modal does not create anything', async ({ page, seeded }) => {
    await page.goto('/categories');
    const before = await page.locator('.category-table tbody tr').count();
    await clickFabAction(page, 'Create Category');
    await page.locator('#category-name').fill('Never saved');
    await page.locator('#category-modal').getByRole('button', { name: 'Cancel' }).click();
    await expect(page.locator('#category-modal')).toBeHidden();
    await page.reload();
    await expect(page.locator('.category-table tbody tr')).toHaveCount(before);
  });

  test('edits a category name, description and parent', async ({ page, seeded }) => {
    await page.goto('/categories');

    await row(page, 'Entertainment').getByTitle('Edit').click();
    const modal = page.locator('#category-modal');
    await expect(modal.locator('#modal-title')).toHaveText('Edit Category');
    await expect(page.locator('#category-id-readonly')).toHaveValue(seeded.ids.categories.Entertainment);
    await expect(page.locator('#category-name')).toHaveValue('Entertainment');

    await page.locator('#category-name').fill('Leisure');
    await page.locator('#category-description').fill('Fun stuff');
    await page.locator('#category-parent').selectOption({ label: 'Food' });
    await modal.getByRole('button', { name: 'Save' }).click();
    await expectToast(page, 'Category updated successfully');

    await expect(row(page, 'Leisure')).toBeVisible();
    await expect(row(page, 'Leisure').locator('.tree-icon')).toBeVisible();
    await expect(row(page, 'Leisure').locator('.category-description')).toHaveText('Fun stuff');
    await expect(row(page, 'Entertainment')).toHaveCount(0);

    // Manually assigned transactions follow the renamed category.
    await page.goto('/review');
    await expect(
      page.locator(`.transaction-card[data-tx-id="${seeded.ids.transactions.cinema}"] .badge-category`)
    ).toHaveText('Leisure');
  });

  test('deletes an unused category after confirmation', async ({ page, seeded }) => {
    await page.goto('/categories');
    await clickFabAction(page, 'Create Category');
    await page.locator('#category-name').fill('Temporary');
    await clickAndWaitForReload(page, page.locator('#category-modal').getByRole('button', { name: 'Save' }));
    await expect(row(page, 'Temporary')).toBeVisible();

    // Dismissing the confirmation keeps the category.
    await row(page, 'Temporary').getByTitle('Delete').click();
    await confirmDialog(page, { accept: false });
    await expect(row(page, 'Temporary')).toBeVisible();

    await row(page, 'Temporary').getByTitle('Delete').click();
    await expect(page.locator('#confirm-message')).toContainText('Temporary');
    await confirmDialog(page);
    await expectToast(page, 'Category deleted successfully');
    await expect(row(page, 'Temporary')).toHaveCount(0);
  });

  test('refuses to delete categories that are still in use', async ({ page, seeded }) => {
    await page.goto('/categories');

    await row(page, 'Food').getByTitle('Delete').click();
    await confirmDialog(page);
    await expectToast(page, 'Cannot delete category with children');

    await row(page, 'Groceries').getByTitle('Delete').click();
    await confirmDialog(page);
    await expectToast(page, 'regex pattern(s) assigned to it');

    await row(page, 'Entertainment').getByTitle('Delete').click();
    await confirmDialog(page);
    await expectToast(page, 'manually assigned transaction(s)');

    await page.reload();
    for (const name of ['Food', 'Groceries', 'Entertainment']) {
      await expect(row(page, name)).toBeVisible();
    }
  });
});
