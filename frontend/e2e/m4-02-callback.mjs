import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = process.env.OPSPILOT_M4_UI_URL;
const password = process.env.OPSPILOT_M4_SUPPORT_PASSWORD;
const directory = process.env.OPSPILOT_M4_SCREENSHOTS;
const resultPath = process.env.OPSPILOT_M4_RESULT_PATH;
const mode = process.env.OPSPILOT_M4_MODE ?? 'journey';
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const http = [];
page.on('response', response => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) http.push({ method: response.request().method(), path: url.pathname, status: response.status() });
});
const get = url => page.evaluate(async url => {
  const response = await fetch(url);
  return { status: response.status, body: await response.json() };
}, url);
async function waitRun(id) {
  await expect.poll(async () => (await get(`/api/runs/${id}`)).body.status,
    { timeout: 240000, intervals: [500,1000,2000] }).not.toMatch(/^(QUEUED|RUNNING|INTERRUPTED_RECOVERABLE)$/);
  const result = (await get(`/api/runs/${id}`)).body;
  expect(result.status).toBe('SUCCEEDED');
  return result;
}
try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(password);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 20000 });
  let created;
  if (mode === 'resume') {
    created = { task_id: process.env.OPSPILOT_M4_TASK_ID, session_id: process.env.OPSPILOT_M4_SESSION_ID };
    await page.locator('.session-item').filter({ hasText:created.session_id.slice(0,22) }).click();
  } else {
    await page.locator('.new-session-button').click();
    await page.getByRole('button', { name: '新建调查任务' }).first().click();
    await page.getByTestId('investigation-kind').selectOption('ASYNC_CALLBACK');
    await page.getByTestId('initial-symptom-input').fill('订单接口返回200，但下游说没收到异步回调。请先查接入知识和适用Skill，再核实当前订单及回调事件，不能重发。');
    await page.screenshot({ path: path.join(directory,'01-user-s3-input.png'), fullPage: true });
    const accepted = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/tasks'));
    await page.getByRole('button', { name: '启动调查' }).click();
    const response = await accepted;
    expect(response.status()).toBe(202);
    created = await response.json();
    await waitRun(created.run_id);
  }
  await expect(page.getByTestId('s3-diagnosis')).toBeVisible({ timeout:30000 });
  await expect(page.getByTestId('s3-diagnosis')).toContainText('接收方仍在排队处理');
  const before = (await get(`/api/tasks/${created.task_id}/inspector`)).body;
  expect(before.trusted_state.s3_outcome.outcome).toBe('RECEIVER_PROCESSING_UNCONFIRMED');
  expect(before.trusted_state.s3_outcome.recovered).toBe(false);
  await page.screenshot({ path: path.join(directory,mode === 'resume' ? '05-after-process-restart.png' : '02-live-diagnosis.png'), fullPage:true });
  let followup = null;
  if (mode !== 'resume') {
    const accepted = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/messages'));
    await page.getByTestId('message-input').fill('请依据刚查到的回调事件解释：200和202分别证明了什么，为什么还不能说下游已经处理成功？只解释现有结果。');
    await page.getByRole('button', { name: '发送消息' }).click();
    followup = await (await accepted).json();
    await waitRun(followup.run_id);
    await expect(page.locator('.message-row.assistant').last()).toBeVisible({ timeout:30000 });
    const answer = await page.locator('.message-row.assistant').last().innerText();
    expect(answer).toMatch(/202|队列|排队|处理/);
    const after = (await get(`/api/tasks/${created.task_id}/inspector`)).body;
    expect(after.trusted_state.control_revision).toBe(before.trusted_state.control_revision);
    expect(after.trusted_state.action_counts).toEqual([]);
    expect(after.runs.filter(r => r.kind !== 'CHAT_READONLY').length).toBe(before.runs.filter(r => r.kind !== 'CHAT_READONLY').length);
    followup.answer = answer;
    followup.inspector_after = after;
    await page.screenshot({ path:path.join(directory,'03-real-model-followup.png'),fullPage:true });
    await page.reload({waitUntil:'domcontentloaded'});
    await expect(page.getByTestId('s3-diagnosis')).toBeVisible({timeout:30000});
    await page.screenshot({path:path.join(directory,'04-after-refresh.png'),fullPage:true});
  }
  const result = { ...created, status:'PASS', mode, inspector:before, followup, http, browser:'Microsoft Edge real browser' };
  await writeFile(resultPath, JSON.stringify(result,null,2), 'utf8');
  console.log(JSON.stringify({ status:'PASS', mode, task_id:created.task_id, session_id:created.session_id }));
} catch (error) {
  await page.screenshot({path:path.join(directory,'failure.png'),fullPage:true}).catch(()=>{});
  await writeFile(resultPath, JSON.stringify({status:'FAIL',message:error.message,http},null,2),'utf8');
  throw error;
} finally {
  await browser.close();
}
