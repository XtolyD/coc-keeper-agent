const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "../src/coc_keeper/web_static/app.js"), "utf8");
// Exercise the actual state/retry helpers and submit handler without a browser.
const helpers = source.slice(0, source.indexOf('const content = document.querySelector'));
const handler = source.slice(source.indexOf("async function sendMessage("), source.indexOf("async function loadCharacters("));

function runtime(storage = new Map()) {
  let sequence = 0;
  const environment = {
    sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    localStorage: {getItem: () => null},
    crypto: {randomUUID: () => `new-id-${++sequence}`},
    renderGame: () => {}, refreshIcons: () => {}, notify: () => {},
  };
  vm.createContext(environment);
  vm.runInContext(helpers + handler, environment);
  return {environment, run: code => vm.runInContext(code, environment)};
}

function form(text) {
  const textarea = {value: text};
  const classes = new Set();
  return {
    textarea,
    querySelector: () => textarea,
    classList: {contains: value => classes.has(value), add: value => classes.add(value), remove: value => classes.delete(value)},
  };
}

test("pending request IDs survive campaign switches and a reload", () => {
  const storage = new Map();
  const first = runtime(storage);
  const idA = first.run("messageRequestId('a', 'damage')");
  const idB = first.run("messageRequestId('b', 'look')");
  assert.notEqual(idA, idB);
  first.run(`completeMessage('a', 'damage', '${idA}')`);
  const reloaded = runtime(storage);
  assert.equal(reloaded.run("messageRequestId('b', 'look')"), idB);
  assert.equal(reloaded.run("Object.keys(state.pendingMessages).length"), 1);
});

test("a failed submit reuses its ID and a successful retry renders the reply", async () => {
  const app = runtime();
  const requests = [];
  let renders = 0;
  app.run("state.activeGame = {id: 'a'}; state.view = 'games'");
  app.environment.renderGame = () => renders++;
  app.environment.api = async (url, options) => {
    requests.push(JSON.parse(options.body));
    if (requests.length === 1) throw new Error("response lost");
    return {game: {id: "a"}};
  };
  const composer = form("damage");
  const event = {preventDefault() {}, currentTarget: composer};
  await app.environment.sendMessage(event);
  assert.equal(composer.textarea.value, "damage");
  await app.environment.sendMessage(event);
  assert.equal(requests[0].request_id, requests[1].request_id);
  assert.equal(app.run("Object.keys(state.pendingMessages).length"), 0);
  assert.equal(renders, 1);
});

test("a late response keeps the currently open campaign", async () => {
  const app = runtime();
  app.run("state.activeGame = {id: 'a'}");
  let resolveResponse;
  let renders = 0;
  app.environment.renderGame = () => renders++;
  app.environment.api = () => new Promise(resolve => {resolveResponse = resolve;});
  const composer = form("damage");
  const sent = app.environment.sendMessage({preventDefault() {}, currentTarget: composer});
  app.run("state.activeGame = {id: 'b'}; messageRequestId('b', 'look')");
  resolveResponse({game: {id: "a"}});
  await sent;
  assert.equal(app.run("state.activeGame.id"), "b");
  assert.equal(app.run("Object.keys(state.pendingMessages).length"), 1);
  assert.equal(renders, 0);
});
