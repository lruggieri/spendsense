// Regex pattern management (/patterns) and its effect on classification.

const {
  test,
  expect,
  expectToast,
  confirmDialog,
  clickFabAction,
  clickAndWaitForReload,
  txCard,
} = require('./fixtures');

const patternRow = (page, name) =>
  page.locator('#patterns-tbody tr', { has: page.locator('.name-col', { hasText: new RegExp(`^${name}$`) }) });

async function createPattern(page, { name, category, rules }) {
  await clickFabAction(page, 'Create Pattern');
  const modal = page.locator('#pattern-modal');
  await expect(modal).toBeVisible();
  await page.locator('#pattern-name').fill(name);
  await page.locator('#pattern-category').selectOption({ label: category });
  for (let i = 0; i < rules.length; i++) {
    if (i > 0) await modal.getByRole('button', { name: '+ Add Rule' }).click();
    const ruleRow = modal.locator('.rule-row').nth(i);
    await ruleRow.locator('.rule-operator').selectOption(rules[i].operator);
    await ruleRow.locator('.rule-keyword').fill(rules[i].keyword);
  }
  await clickAndWaitForReload(page, modal.getByRole('button', { name: 'Save' }));
  await expect(patternRow(page, name)).toBeVisible();
}

test.describe('Patterns', () => {
  test('lists patterns with their description and category', async ({ page, seeded }) => {
    await page.goto('/patterns');
    await expect(page.locator('#patterns-tbody tr')).toHaveCount(2);
    await expect(page.locator('#patterns-tbody .name-col')).toHaveText(['Supermarket', 'Transit']);
    await expect(patternRow(page, 'Supermarket').locator('.category-col')).toHaveText('Groceries');
    await expect(patternRow(page, 'Transit').locator('.category-col')).toHaveText('Transport');
    await expect(patternRow(page, 'Transit').locator('.pattern-description')).toContainText('METRO');
    await expect(patternRow(page, 'Transit').locator('.pattern-description')).toContainText('TAXI');
  });

  test('builds a multi-rule pattern with a live preview @mobile', async ({ page, seeded }) => {
    await page.goto('/patterns');
    await clickFabAction(page, 'Create Pattern');

    const modal = page.locator('#pattern-modal');
    const preview = page.locator('#preview-description');
    await expect(preview).toHaveText('No rules added yet');
    await expect(modal.locator('.rule-row')).toHaveCount(1);

    await modal.locator('.rule-keyword').first().fill('BISTRO');
    await expect(preview).toHaveText('Contains BISTRO');

    await modal.getByRole('button', { name: '+ Add Rule' }).click();
    await modal.locator('.rule-row').nth(1).locator('.rule-operator').selectOption('NOT');
    await modal.locator('.rule-row').nth(1).locator('.rule-keyword').fill('Downtown');
    await expect(preview).toHaveText('Contains BISTRO, Must NOT contain Downtown');

    await modal.getByRole('button', { name: '+ Add Rule' }).click();
    await modal.locator('.rule-row').nth(2).locator('.rule-operator').selectOption('START_WITH');
    await modal.locator('.rule-row').nth(2).locator('.rule-keyword').fill('Le');
    await expect(preview).toHaveText('Starts with Le, Contains BISTRO, Must NOT contain Downtown');

    // Removing a rule updates the preview.
    await modal.locator('.rule-row').nth(2).getByTitle('Remove rule').click();
    await expect(modal.locator('.rule-row')).toHaveCount(2);
    await expect(preview).toHaveText('Contains BISTRO, Must NOT contain Downtown');
  });

  test('validates names, categories and rules', async ({ page, seeded }) => {
    await page.goto('/patterns');
    await clickFabAction(page, 'Create Pattern');
    const save = page.locator('#pattern-modal').getByRole('button', { name: 'Save' });

    await save.click();
    await expectToast(page, 'Pattern name is required');

    await page.locator('#pattern-name').fill('Only negative');
    await save.click();
    await expectToast(page, 'Target category is required');

    // Child categories are indented with non-breaking spaces, so select by id.
    await page.locator('#pattern-category').selectOption(seeded.ids.categories.Groceries);
    await save.click();
    await expectToast(page, 'At least one rule is required');

    await page.locator('.rule-operator').first().selectOption('NOT');
    await page.locator('.rule-keyword').first().fill('ATM');
    await save.click();
    await expectToast(page, 'Pattern must have at least one positive rule');
  });

  test('a new pattern re-classifies matching transactions', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto(`/review`);
    await expect(txCard(page, tx.bistro2).locator('.badge-source')).toHaveText('SIMILARITY');

    await page.goto('/patterns');
    await createPattern(page, {
      name: 'Downtown',
      category: 'Entertainment',
      rules: [{ operator: 'END_WITH', keyword: 'Downtown' }],
    });

    await page.goto('/review');
    await expect(txCard(page, tx.bistro2).locator('.badge-category')).toHaveText('Entertainment');
    await expect(txCard(page, tx.bistro2).locator('.badge-source')).toHaveText('REGEXP');
    // Manual assignments still win over patterns.
    await expect(txCard(page, tx.bistro).locator('.badge-source')).toHaveText('MANUAL');
  });

  test('edits a pattern', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/patterns');

    await patternRow(page, 'Transit').getByTitle('Edit').click();
    const modal = page.locator('#pattern-modal');
    await expect(modal.locator('#modal-title')).toHaveText('Edit Pattern');
    await expect(page.locator('#pattern-name')).toHaveValue('Transit');
    await expect(modal.locator('.rule-row')).toHaveCount(2);
    await expect(modal.locator('.rule-keyword').nth(0)).toHaveValue('METRO');
    await expect(modal.locator('.rule-keyword').nth(1)).toHaveValue('TAXI');

    // Drop the TAXI rule and retarget the pattern.
    await modal.locator('.rule-row').nth(1).getByTitle('Remove rule').click();
    await page.locator('#pattern-name').fill('Metro only');
    await page.locator('#pattern-category').selectOption({ label: 'Entertainment' });
    await modal.getByRole('button', { name: 'Save' }).click();
    await expectToast(page, 'Pattern updated successfully');
    await expect(patternRow(page, 'Metro only').locator('.category-col')).toHaveText('Entertainment');
    await expect(patternRow(page, 'Transit')).toHaveCount(0);

    await page.goto('/review');
    await expect(txCard(page, tx.metro).locator('.badge-category')).toHaveText('Entertainment');
    await expect(txCard(page, tx.taxi_old).locator('.badge-source', { hasText: 'REGEXP' })).toHaveCount(0);
  });

  test('deletes a pattern after confirmation', async ({ page, seeded }) => {
    await page.goto('/patterns');

    await patternRow(page, 'Supermarket').getByTitle('Delete').click();
    await confirmDialog(page, { accept: false });
    await expect(patternRow(page, 'Supermarket')).toBeVisible();

    await patternRow(page, 'Supermarket').getByTitle('Delete').click();
    await confirmDialog(page);
    await expectToast(page, 'Pattern deleted successfully');
    await expect(patternRow(page, 'Supermarket')).toHaveCount(0);
    await expect(page.locator('#patterns-tbody tr')).toHaveCount(1);
  });

  test('drag-and-drop reordering changes which pattern wins', async ({ page, seeded }) => {
    const tx = seeded.ids.transactions;
    await page.goto('/patterns');
    await createPattern(page, {
      name: 'Express',
      category: 'Entertainment',
      rules: [{ operator: 'OR', keyword: 'EXPRESS' }],
    });
    await expect(page.locator('#patterns-tbody .name-col')).toHaveText(['Supermarket', 'Transit', 'Express']);

    // "SUPERMARKET EXPRESS" matches both; the first pattern wins.
    await page.goto('/review');
    await expect(txCard(page, tx.market_old).locator('.badge-category')).toHaveText('Groceries');

    await page.goto('/patterns');
    await patternRow(page, 'Express').dragTo(patternRow(page, 'Supermarket'));
    await expectToast(page, 'Pattern order updated');
    await expect(page.locator('#patterns-tbody .name-col')).toHaveText(['Express', 'Supermarket', 'Transit']);

    await page.reload();
    await expect(page.locator('#patterns-tbody .name-col')).toHaveText(['Express', 'Supermarket', 'Transit']);

    await page.goto('/review');
    await expect(txCard(page, tx.market_old).locator('.badge-category')).toHaveText('Entertainment');
  });
});
