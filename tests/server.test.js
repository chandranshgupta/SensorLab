// Server validation aur protocol compliance unit tests

const test = require('node:test');
const assert = require('node:assert');
const { validateSensorMessage } = require('../server/index.js');

test('Valid phone accelerometer message accept hona chahiye', () => {
  const validMsg = {
    source: 'phone',
    sensor: 'accel',
    values: [0.12, -9.81, 0.05],
    time: 1730373000
  };
  assert.strictEqual(validateSensorMessage(validMsg), true);
});

test('Valid board sensor message accept hona chahiye', () => {
  const validMsg = {
    source: 'board',
    sensor: 'temp',
    values: [26.5],
    time: 1730373005
  };
  assert.strictEqual(validateSensorMessage(validMsg), true);
});

test('Valid simulator drone message accept hona chahiye', () => {
  const validMsg = {
    source: 'sim',
    sensor: 'orientation',
    values: [15.0, -5.2, 0.0],
    time: 1730373010
  };
  assert.strictEqual(validateSensorMessage(validMsg), true);
});

test('Invalid source reject hona chahiye', () => {
  const invalidMsg = {
    source: 'unauthorized_device',
    sensor: 'accel',
    values: [1, 2, 3],
    time: 1730373000
  };
  assert.strictEqual(validateSensorMessage(invalidMsg), false);
});

test('Empty sensor name reject hona chahiye', () => {
  const invalidMsg = {
    source: 'phone',
    sensor: '   ',
    values: [1, 2, 3],
    time: 1730373000
  };
  assert.strictEqual(validateSensorMessage(invalidMsg), false);
});

test('Non-numeric values array reject hona chahiye', () => {
  const invalidMsg = {
    source: 'sim',
    sensor: 'accel',
    values: ['text_string', 42],
    time: 1730373000
  };
  assert.strictEqual(validateSensorMessage(invalidMsg), false);
});

test('Negative timestamp reject hona chahiye', () => {
  const invalidMsg = {
    source: 'phone',
    sensor: 'accel',
    values: [0, 0, 0],
    time: -100
  };
  assert.strictEqual(validateSensorMessage(invalidMsg), false);
});

