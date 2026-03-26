const fs = require("fs");
const vm = require("vm");

const payloadPath = process.argv[2];
const payload = JSON.parse(fs.readFileSync(payloadPath, "utf8"));
const profile = payload.browser_profile || {};
const scripts = Array.isArray(payload.scripts)
  ? payload.scripts
  : [{ url: payload.url, content: payload.script || "" }];
const cookies = {};
const loadListeners = [];

const document = {
  body: {},
  getElementById() {
    return { innerHTML: "" };
  },
  createElement() {
    return {
      getContext() {
        return {
          textBaseline: "",
          font: "",
          fillStyle: "",
          fillRect() {},
          fillText() {},
        };
      },
      toDataURL() {
        return profile.canvas_fingerprint || "data:,";
      },
    };
  },
};

Object.defineProperty(document, "cookie", {
  get() {
    return Object.entries(cookies)
      .map(([key, value]) => `${key}=${value}`)
      .join("; ");
  },
  set(value) {
    const pair = String(value).split(";")[0];
    const idx = pair.indexOf("=");
    if (idx === -1) {
      return;
    }
    const name = pair.slice(0, idx).trim();
    const cookieValue = pair.slice(idx + 1).trim();
    cookies[name] = cookieValue;
  },
});

const navigatorObject = {
  userAgent: profile.user_agent || "",
  language: profile.language || "en-US",
  platform: profile.platform || "MacIntel",
  cpuClass: profile.cpu_class || "",
  doNotTrack: profile.do_not_track || "",
  maxTouchPoints: Number(profile.max_touch_points || 0),
  msMaxTouchPoints: Number(profile.ms_max_touch_points || 0),
  plugins: [],
  mimeTypes: [],
  cookieEnabled: true,
  javaEnabled() {
    return false;
  },
};

const screenObject = {
  colorDepth: Number(profile.color_depth || 24),
  width: Number(profile.screen_width || 1920),
  height: Number(profile.screen_height || 1080),
  availWidth: Number(profile.screen_width || 1920),
  availHeight: Number(profile.screen_height || 1080),
};

const context = {
  console,
  document,
  navigator: navigatorObject,
  screen: screenObject,
  location: new URL(payload.url),
  window: {},
  self: {},
  top: {},
  parent: {},
  setTimeout(fn) {
    if (typeof fn === "function") {
      fn();
    }
    return 0;
  },
  clearTimeout() {},
  setInterval(fn) {
    if (typeof fn === "function") {
      fn();
    }
    return 0;
  },
  clearInterval() {},
  atob(value) {
    return Buffer.from(value, "base64").toString("binary");
  },
  btoa(value) {
    return Buffer.from(value, "binary").toString("base64");
  },
  Date,
};

context.window = context;
context.self = context;
context.top = context;
context.parent = context;
context.window.document = document;
context.window.navigator = navigatorObject;
context.window.screen = screenObject;
context.window.localStorage = {};
context.window.sessionStorage = {};
context.window.indexedDB = {};
context.window.openDatabase = profile.open_database_type === "undefined" ? undefined : function () {};
context.window.addEventListener = function (event, handler) {
  if (event === "load" && typeof handler === "function") {
    loadListeners.push(handler);
  }
};
context.location.reload = function () {};

try {
  for (const item of scripts) {
    vm.runInNewContext(item.content, context, { timeout: 1500 });
  }
  for (const handler of loadListeners) {
    handler({ type: "load" });
  }
  process.stdout.write(JSON.stringify(cookies));
} catch (err) {
  process.stdout.write(
    JSON.stringify({
      __solver_error__: {
        name: err && err.name ? err.name : "Error",
        message: err && err.message ? err.message : String(err),
      },
      __cookies__: cookies,
    })
  );
}
