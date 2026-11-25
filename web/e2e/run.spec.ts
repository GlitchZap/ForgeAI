import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const RUN = process.env.FORGE_E2E_RUN ?? 'hr_policy'

async function openRun(page: Page, id = RUN) {
  await page.goto(`/#run/${id}`)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.locator('canvas')).toBeVisible({ timeout: 15_000 })
}

test('finished run shows score, chart and the honest verdict', async ({ page }) => {
  await openRun(page)
  await expect(page.locator('dt', { hasText: 'Score' })).toBeVisible()
  await expect(page.locator('dt', { hasText: 'Holdout' })).toBeVisible()
  await expect(page.getByText(/tests, so its true score is probably between \d+% and \d+%/)).toBeAttached()
  await expect(page.getByRole('status')).toContainText('Finished')
})

test('a failing case from the legend opens its trace', async ({ page }) => {
  await openRun(page)
  await page.getByLabel('Legend and trust').getByRole('button').first().click()
  const trace = page.getByLabel('Case trace')
  await expect(trace.getByText(/^Failed: /)).toBeVisible()
  await expect(trace.getByRole('heading', { level: 2, name: /^[a-z]{3}-\d{2}$/ })).toBeVisible()
  for (const step of ['Expected', 'Retrieved', 'Answer', 'Judged']) await expect(trace.getByRole('heading', { name: step })).toBeVisible()
})

test('a row in the Tests section opens its trace', async ({ page }) => {
  await page.goto(`/#run/${RUN}/tests`)
  const row = page.getByRole('row').nth(1)
  const id = (await row.getByRole('cell').first().innerText()).trim()
  await row.click()
  await expect(page.getByLabel('Case trace').getByRole('heading', { level: 2, name: id })).toBeVisible()
})

test('no serious or critical accessibility violations', async ({ page }) => {
  await openRun(page)
  const r = await new AxeBuilder({ page }).exclude('canvas').analyze()
  const bad = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(bad.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target}`)).toEqual([])
})

for (const [w, h] of [[1366, 768], [1920, 1080], [375, 812]] as const) {
  test(`screenshot ${w}x${h}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await openRun(page)
    await page.waitForTimeout(800)
    await page.screenshot({ path: `e2e/screenshots/run-${w}x${h}.png`, fullPage: true })
  })
}

test('checkpoint: edits to the requirements are what gets approved', async ({ page }) => {
  const id = 'e2e-checkpoint'
  const req = { title: 'HR assistant', scope: 'Leave and travel policy.', audience: 'shore staff', tone: 'precise',
    must_answer: [{ name: 'leave', description: 'annual leave', source_hint: 'documents' }], must_refuse: ['Legal advice'],
    clarifications: [], groundability: [], flags: [] }
  let posted: { must_refuse: string[] } | null = null
  await page.route('**/api/runs', (r) => r.fulfill({ json: [{ id, name: 'Checkpoint demo', status: 'awaiting_approval', updated: 0 }] }))
  await page.route(`**/api/runs/${id}/events`, (r) => r.fulfill({
    status: 200, headers: { 'content-type': 'text/event-stream' },
    body: [{ ts: 1, stage: 'ingest', status: 'done', documents: 1, chunks: 3, mode: 'bm25' },
           { ts: 2, stage: 'checkpoint', status: 'waiting' }].map((e) => `data: ${JSON.stringify(e)}\n\n`).join('') + 'event: end\ndata: {}\n\n',
  }))
  await page.route(`**/api/runs/${id}/artifacts/**`, (r) => r.fulfill({ status: 404, json: { detail: 'not produced (yet)' } }))
  await page.route(`**/api/runs/${id}/checkpoint`, async (r) => {
    if (r.request().method() === 'POST') { posted = r.request().postDataJSON(); return r.fulfill({ json: { ok: true } }) }
    return r.fulfill({ json: req })
  })
  await page.goto(`/#run/${id}`)
  await expect(page.getByRole('link', { name: /Requirements \(needs approval\)/ })).toHaveAttribute('aria-current', 'page')
  await page.getByLabel('Must refuse, one per line').fill('Legal advice\nQuestions about the office canteen')
  await page.getByRole('button', { name: 'Approve and build the agent' }).click()
  await expect.poll(() => posted?.must_refuse).toEqual(['Legal advice', 'Questions about the office canteen'])
})

test('home explains the service and links into the app', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'forgeai' })).toBeVisible()
  for (const h of ['from a paragraph to a tested agent', 'every step shows its working', 'only the tools a brief needs'])
    await expect(page.getByRole('heading', { name: h })).toBeVisible()
  await expect(page.getByRole('tab', { name: /Requirements/ })).toBeVisible()
  await page.getByRole('radio', { name: /weather/ }).click()
  await expect(page.getByRole('table')).toContainText('Port call planner')
  await page.getByRole('button', { name: 'Start a run' }).first().click()
  await expect(page).toHaveURL(/#new$/)
  await expect(page.getByRole('heading', { name: 'build an agent from a brief' })).toBeVisible()
})

test('home has no serious accessibility violations', async ({ page }) => {
  await page.goto('/')
  await page.waitForTimeout(1500)
  const r = await new AxeBuilder({ page }).exclude('canvas').analyze()
  const bad = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(bad.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target}`)).toEqual([])
})

test('logbook lists runs and every run section opens', async ({ page }) => {
  await page.goto('/#runs')
  await expect(page.getByRole('heading', { name: 'logbook' })).toBeVisible()
  await page.getByRole('link', { name: /hr policy assistant/i }).first().click()
  for (const [section, text] of [['fixes', /fix 1/i], ['requirements', /Can the documents support it/], ['report', /ForgeAI report/]] as const) {
    await page.getByRole('link', { name: new RegExp(`^${section}`, 'i') }).first().click()
    await expect(page.getByText(text).first()).toBeVisible()
  }
})

test('phones get a navigation drawer', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/#runs')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.locator('a[href="#new"]:visible').first().click()
  await expect(page).toHaveURL(/#new$/)
})

test('the agent answers a question with a cited source (real model)', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto(`/#run/${RUN}/chat`)
  await page.getByLabel('Your question').fill('How many days of sick leave do I get each year?')
  await page.getByLabel('Your question').press('Enter')
  await expect(page.getByText(/12 days/)).toBeVisible({ timeout: 120_000 })
  await expect(page.getByText(/leave_policy\.pdf#\d+/)).toBeVisible()
})

for (const [w, h, tag] of [[1366, 768, 'desktop'], [375, 812, 'mobile']] as const) {
  test(`home screenshot ${tag}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })  // settle entrance motion so the capture shows final state
    await page.setViewportSize({ width: w, height: h })
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1, name: 'forgeai' })).toBeVisible()
    await page.waitForTimeout(1500)
    await page.screenshot({ path: `e2e/screenshots/home-${tag}.png`, fullPage: true })
  })
}

test('review captures: chat exchange and open drawers', async ({ page }) => {
  test.setTimeout(240_000)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 1366, height: 768 })
  await page.goto(`/#run/${RUN}/chat`)
  await page.getByLabel('Your question').fill('How many days of sick leave do I get each year?')
  await page.getByLabel('Your question').press('Enter')
  await expect(page.getByText(/12 days/)).toBeVisible({ timeout: 180_000 })
  await expect(page.getByLabel('Your question')).toBeFocused()  // focus comes back after the reply
  await page.screenshot({ path: 'e2e/screenshots/chat-1366.png' })
  await page.setViewportSize({ width: 375, height: 812 })
  await page.screenshot({ path: 'e2e/screenshots/chat-375.png' })
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.waitForTimeout(500)
  await page.screenshot({ path: 'e2e/screenshots/app-drawer-375.png' })
  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.waitForTimeout(500)
  await page.screenshot({ path: 'e2e/screenshots/home-drawer-375.png' })
})

test('new run: a chosen set can be cleared, and Back leaves the page', async ({ page }) => {
  await page.goto('/#runs')
  await page.goto('/#new')
  const hr = page.getByRole('radio', { name: /hr policy/ })
  await hr.click()
  await expect(hr).toHaveAttribute('aria-checked', 'true')
  await expect(page.getByRole('button', { name: /^Next/ })).toBeEnabled()
  await hr.click()
  await expect(hr).toHaveAttribute('aria-checked', 'false')
  await expect(page.getByRole('button', { name: /^Next/ })).toBeDisabled()
  await page.getByRole('button', { name: 'Back' }).click()
  await expect(page).toHaveURL(/#runs$/)
})

test('chat history is saved and can be reopened after a reload', async ({ page }) => {
  await page.goto(`/#run/${RUN}/chat`)
  await page.evaluate((r) => localStorage.setItem(`forgeai.chats.${r}`, JSON.stringify([{ id: 'x1', title: 'Saved question about leave', updated: Date.now(),
    msgs: [{ role: 'user', content: 'Saved question about leave' }, { role: 'assistant', content: 'Saved answer: 24 working days.', seconds: 3,
      trace: { question: 'q', retrieved: ['leave_policy.pdf#2'], retrieved_docs: [], tool_calls: [], reply: { answer: 'Saved answer: 24 working days.', citations: ['leave_policy.pdf#2'], refused: false, refusal_reason: '' } } }] }])), RUN)
  await page.reload()
  await page.getByRole('button', { name: /^Saved question about leave/ }).click()
  await expect(page.getByText('Saved answer: 24 working days.')).toBeVisible()
  await page.getByRole('button', { name: 'New conversation' }).click()
  await expect(page.getByText('ask it something')).toBeVisible()
})

test('an answer survives a page refresh while it is being written (real model)', async ({ page }) => {
  test.setTimeout(240_000)
  await page.goto(`/#run/${RUN}/chat`)
  await page.evaluate((r) => localStorage.removeItem(`forgeai.chats.${r}`), RUN)
  await page.reload()
  await page.getByLabel('Your question').fill('How many days of paid sick leave do employees receive?')
  await page.getByLabel('Your question').press('Enter')
  await expect(page.getByLabel('The agent is answering')).toBeVisible()
  await page.reload()  // mid-answer
  await expect(page.getByText(/12 days/).first()).toBeVisible({ timeout: 200_000 })
})

test('light theme switch persists and the sidebar collapses on demand', async ({ page }) => {
  await page.goto('/#runs')
  await page.getByRole('switch', { name: 'Light theme' }).click()
  await expect(page.locator('html')).toHaveClass(/light/)
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/light/)
  await page.getByRole('switch', { name: 'Light theme' }).click()
  await page.getByRole('button', { name: 'Collapse sidebar' }).click()
  await expect(page.getByRole('button', { name: 'Expand sidebar' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Expand sidebar' })).toBeVisible()  // remembered
  await page.getByRole('button', { name: 'Expand sidebar' }).click()
})
