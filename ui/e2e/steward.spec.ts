import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const BRIEF = '/batches/b_01J9ZK2A7T/findings'

test('smoke: batches list, overview and review queue show the brief findings', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/batches$/)
  await page.getByRole('link', { name: 'b_01J9ZK2A7T' }).click()
  await expect(page.getByRole('heading', { name: 'b_01J9ZK2A7T' })).toBeVisible()
  await page.getByRole('link', { name: 'Review findings' }).click()
  await expect(page.getByText("Manufacturer 'SKF' is present")).toBeVisible()
  await expect(page.getByRole('row')).toHaveCount(4) // header + 3 findings
})

test('filters live in the URL and survive a reload', async ({ page }) => {
  await page.goto(BRIEF)
  await page.getByRole('radio', { name: 'Low' }).check()
  await expect(page).toHaveURL(/severity=low/)
  await page.reload()
  await expect(page.getByRole('radio', { name: 'Low' })).toBeChecked()
  await expect(page.getByRole('row')).toHaveCount(2)
})

test('keyboard only: move, open, investigate-by-button, close', async ({ page }) => {
  await page.goto(BRIEF)
  const first = page.locator('tr[data-index="0"]')
  await first.focus()
  await page.keyboard.press('j')
  await expect(page.locator('tr[data-index="1"]')).toBeFocused()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: 'Finding detail' })
  await expect(drawer).toBeVisible()
  await expect(page).toHaveURL(/finding=/)
  await drawer.getByRole('button', { name: 'Investigate' }).focus()
  await page.keyboard.press('Enter')
  await expect(drawer.getByText('Decided:')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(page.locator('tr[data-index="1"]')).toBeFocused() // focus returns to the row
})

test('no horizontal overflow at 320 px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 })
  await page.goto(BRIEF)
  await expect(page.getByText("Manufacturer 'SKF'")).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})

for (const [name, url] of [['batch list', '/batches'], ['upload', '/batches/new'], ['review queue', BRIEF], ['batch overview', '/batches/b_01J9ZK2A7T']] as const) {
  test(`axe: no serious or critical violations on ${name}`, async ({ page }) => {
    await page.goto(url)
    await page.waitForLoadState('networkidle')
    const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze()
    expect(violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')).toEqual([])
  })
}
