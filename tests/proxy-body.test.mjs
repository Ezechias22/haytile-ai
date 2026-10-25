import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BodyTooLarge, readBoundedBody } from '../apps/web/app/api/body-limit.ts';

test('chunked upload exceeding the limit is cancelled before reading the rest', async () => {
  let cancelled = false;
  let reads = 0;
  const stream = new ReadableStream({
    pull(controller) { reads++; controller.enqueue(new Uint8Array(4)); },
    cancel() { cancelled = true; },
  }, { highWaterMark: 0 });
  await assert.rejects(readBoundedBody(stream, 6), BodyTooLarge);
  assert.equal(cancelled, true);
  assert.equal(reads, 2);
});

test('valid multipart bytes are preserved exactly across chunks', async () => {
  const source = [new Uint8Array([0, 255]), new Uint8Array([10, 13])];
  const stream = new ReadableStream({ start(c) { for (const p of source) c.enqueue(p); c.close(); } });
  assert.deepEqual(await readBoundedBody(stream, 4), new Uint8Array([0, 255, 10, 13]));
});
