import asyncio
import atexit
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import logging
import math
import random
import shutil
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx
from curl_cffi.requests import AsyncSession

from config import GeetokenConfig, ProxyConfig, runtime_config
from database import GEETOKEN_FAILURE_GATE, get_geetokens_db, init_geetokens_db
from http_client import BROWSER_PROFILES_ANDROID, _get_extra_fp, _select_browser_profile

DEFAULT_GEETEST_APPID = "9ia4hndgblg9xihxcwgdjt9ztg8sjwaf"


class GeetestRateLimitError(RuntimeError):
    """HTTP 567 no pre_load do riskct.geetest.com — IP sob rate-limit do GeeTest."""

logger = logging.getLogger(__name__)


def _hidden_subprocess_kwargs() -> Dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def _node_executable() -> str:
    """Prefer the bundled Node runtime and fall back to the system PATH."""
    app_dir = os.path.dirname(os.path.abspath(getattr(sys, "executable", "") or os.getcwd()))
    candidates = [
        os.path.join(app_dir, "node", "node.exe"),
        os.path.join(app_dir, "node", "node"),
    ]
    if not getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "node", "node.exe"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("node") or "node"


def _configured_default_platform_url() -> str:
    return GeetokenConfig().plataforma_padrao.strip()

DEFAULT_SS_DESKTOP_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
_REAL_DEFAULT_ENV_TEMPLATE = {
    "g1": 12,
    "g2": 8,
    "g3": [932, 430],
    "g4": 24,
    "g5": False,
    "g6": [0, 0, 0, 0],
    "g7": {"mtp": 0, "te": False, "ts": False},
    "g8": "Linux x86_64",
    "g9": "Google Inc.",
    "g10": [
        "PDF Viewer",
        "Chrome PDF Viewer",
        "Chromium PDF Viewer",
        "Microsoft Edge PDF Viewer",
        "WebKit built-in PDF",
    ],
    "g13": 255,
    "g14": "696241cea566ef9e6be0969ca1f39ab3",
    "g15": -1,
    "g16": "",
    "g17": -1,
    "g18": 8.32115e-05,
    "g19": [],
    "g20": "018712662df42f2dee138ab7e477e0c5",
    "g21": "d84f78e208b86bc0ecf0d6b000c0f66b",
    "g22": "cf252fdcd0c577918a558e3d5869780d",
    "g23": "America/Sao_Paulo",
    "g24": "66f2b1286261e847329eeba0d40294ce",
    "g25": "srgb",
    "g26": 0,
    "g27": False,
    "g29": 0,
    "g30": False,
    "g31": ["chrome"],
    "g32": True,
    "g33": True,
    "g34": True,
    "g35": False,
    "g36": -1,
    "g37": "c1265f087d7eb4d9dbc626f73982db0c",
    "t38": [0.09999999403953552, 0.10000002384185791],
    "g39": 4239130624,
    "g40": {
        "x": 8,
        "y": 8,
        "left": 8,
        "right": 271.390625,
        "bottom": 25,
        "height": 17,
        "top": 8,
        "width": 263.390625,
        "font": '"Times New Roman"',
    },
    "g41": {
        "x": 8,
        "y": 9,
        "left": 8,
        "right": 1605.078125,
        "bottom": 26,
        "height": 17,
        "top": 9,
        "width": 1597.078125,
        "font": '"Times New Roman"',
    },
    "g42": "calc(0.207912px)",
    "r1": [],
    "r2": [],
    "r3": False,
    "r4": False,
    "r5": False,
    "r6": [],
    "r7": [],
    "r8": ["1", "1", "border-box border-box", ""],
    "r9": False,
    "r10": False,
    "r11": DEFAULT_SS_DESKTOP_UA,
    "r12": False,
    "r13": "",
    "r14": True,
    "r15": [],
    "r16": {"ow": 500, "oh": 932, "iw": 500, "ih": 845},
    "r17": {"ps": "20030107", "pf": "Linux x86_64", "hp": True},
    "r18": 33,
    "r19": {
        "browser": {"name": "Chrome", "version": "145.0.0.0", "major": "145"},
        "device": {},
        "engine": {"name": "Blink", "version": "145.0.0.0"},
        "os": {"name": "Linux"},
    },
}
_REAL_DEFAULT_DU_TEMPLATE = {
    "g1": 0,
    "g2": 0,
    "g3": 0,
    "g4": 0,
    "g5": 1,
    "g7": 1,
    "g8": 0,
    "g9": 0,
    "g10": 1,
    "g11": 0,
    "g12": 0,
    "g13": 0,
    "g15": 1,
    "g16": 0,
    "g17": 0,
    "g14": 15,
    "g20": 15,
    "g19": 74,
    "g21": 13,
    "g23": 6,
    "g24": 18,
    "g25": 0,
    "g26": 0,
    "g27": 0,
    "g28": 0,
    "g29": 1,
    "g30": 0,
    "g31": 0,
    "g32": 0,
    "g33": 0,
    "g34": 0,
    "g35": 0,
    "g36": 0,
    "g37": 1,
    "t38": 12,
    "g39": 0,
    "g40": 22,
    "g41": 14,
    "g42": 0,
    "r2": 1,
    "r3": 0,
    "r4": 0,
    "r5": 0,
    "r6": 0,
    "r1": 13,
    "r7": 3,
    "r8": 2,
    "r9": 0,
    "r11": 12,
    "r13": 0,
    "r14": 1,
    "r15": 6,
    "r12": 9,
    "r16": 0,
    "r17": 0,
    "r18": 0,
    "r19": 1,
    "g18": 79,
    "g6": 1,
    "r10": 101,
    "g22": 601,
}
_REAL_DEFAULT_TU_TEMPLATE = {"et": 706, "st": 194, "lt": 237, "kt": 13}

_NODE_RUNNER_SCRIPT = r"""
const vm = require('vm');
const nodeCrypto = require('crypto');
const nodeWebCrypto = nodeCrypto.webcrypto || {};
const BlobCtor = globalThis.Blob;
const FileCtor = globalThis.File;
const HeadersCtor = globalThis.Headers;
const RequestCtor = globalThis.Request;
const ResponseCtor = globalThis.Response;
const FormDataCtor = globalThis.FormData;
const AbortControllerCtor = globalThis.AbortController;
const AbortSignalCtor = globalThis.AbortSignal;
const ReadableStreamCtor = globalThis.ReadableStream;
const WritableStreamCtor = globalThis.WritableStream;
const TransformStreamCtor = globalThis.TransformStream;
const TextEncoderCtor = globalThis.TextEncoder;
const TextDecoderCtor = globalThis.TextDecoder;
const EventTargetCtor = globalThis.EventTarget;
const EventCtor = globalThis.Event;
const CustomEventCtor = globalThis.CustomEvent;
const DOMExceptionCtor = globalThis.DOMException;
const MessageChannelCtor = globalThis.MessageChannel;
const MessagePortCtor = globalThis.MessagePort;

async function main(input){
  if (!input) input = JSON.parse(require('fs').readFileSync(0, 'utf8') || '{}');
  const gtJs = String(input.gt_js || '');
  const geeguardJs = String(input.geeguard_js || '');
  const appId = String(input.appid || '');
  const prePayload = input.pre_payload && typeof input.pre_payload === 'object' ? input.pre_payload : {};
  const profilePatch = input.profile_patch && typeof input.profile_patch === 'object' ? input.profile_patch : null;
  const userAgent = String(input.user_agent || 'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36');
  const language = String(input.language || 'pt-BR');
  const targetPageUrl = String(input.target_page_url || 'https://example.com/');
  const isAndroid = userAgent.toLowerCase().includes('android');
  const parsedTarget = (() => { try { return new URL(targetPageUrl); } catch (_) { return new URL('https://example.com/'); } })();

  const logs = [];
  const bodyCandidates = [];
  const seededGtUid = nodeCrypto.randomBytes(16).toString('hex');
  const capture = {
    clientReportBody: '',
    clientReportUrl: '',
    clientReportHeaders: {},
  };
  let captureDone = false;
  let resolveCapture = null;
  const capturePromise = new Promise((resolve) => {
    resolveCapture = resolve;
  });
  const pushLog = (item) => {
    if (logs.length >= 120) logs.shift();
    logs.push(item);
  };
  const normalizeBody = (raw) => {
    const text = String(raw == null ? '' : raw).trim();
    if (text.length >= 2 && text[0] === '"' && text[text.length - 1] === '"') {
      return text.slice(1, -1).trim();
    }
    return text;
  };
  const consoleShim = {
    log(){}, info(){}, warn(){},
    error(...args){
      for (const arg of args) {
        try { String(arg); } catch (_) {}
      }
    },
  };
  const nativeFn = (name, impl) => {
    try { Object.defineProperty(impl, 'name', { value: name, configurable: true }); } catch (_) {}
    impl.toString = () => `function ${name}() { [native code] }`;
    return impl;
  };
  const normalizeForJson = (value, depth = 0) => {
    if (depth > 6) return '[depth-limit]';
    const ctorName = value && value.constructor && value.constructor.name ? String(value.constructor.name) : '';
    const looksLikeError = !!(
      value &&
      typeof value === 'object' &&
      (
        value instanceof Error ||
        ctorName.includes('Error') ||
        ctorName.includes('Exception') ||
        typeof value.message === 'string' ||
        typeof value.stack === 'string'
      )
    );
    if (looksLikeError) {
      return {
        name: String(value.name || ctorName || 'Error'),
        message: String(value.message || ''),
        stack: String(value.stack || '').slice(0, 600),
      };
    }
    if (Array.isArray(value)) {
      return value.map((item) => normalizeForJson(item, depth + 1));
    }
    if (!value || typeof value !== 'object') return value;
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[String(key)] = normalizeForJson(item, depth + 1);
    }
    return out;
  };
  const emitResult = (obj) => {
    const line = `${JSON.stringify(normalizeForJson(obj))}\n`;
    if (process.env.GEETOKEN_NODE_PERSISTENT === '1') {
      process.stdout.write(line);
      return;
    }
    try {
      process.stdout.write(line, () => process.exit(0));
    } catch (_) {
      process.stdout.write(line);
      process.exit(0);
    }
  };
  const nativeSetInterval = setInterval;
  const cloneJson = (value) => {
    if (value == null) return value;
    try { return JSON.parse(JSON.stringify(value)); } catch (_) { return value; }
  };
  const safeSetInterval = (...args) => {
    const timer = nativeSetInterval(...args);
    try {
      if (timer && typeof timer.unref === 'function') timer.unref();
    } catch (_) {}
    return timer;
  };
  const mkPluginArray = () => {
    const items = [
      { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Portable Document Format' },
    ];
    items.item = (index) => items[index] || null;
    items.namedItem = (name) => items.find((item) => item && item.name === name) || null;
    return items;
  };
  const mkMimeTypeArray = () => {
    const items = [
      { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
      { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
    ];
    items.item = (index) => items[index] || null;
    items.namedItem = (name) => items.find((item) => item && item.type === name) || null;
    return items;
  };
  const mkCaches = () => ({
    keys: async () => [],
    open: async (name) => ({
      name: String(name || ''),
      keys: async () => [],
      match: async () => undefined,
      put: async () => undefined,
    }),
    has: async () => false,
    delete: async () => true,
    match: async () => undefined,
  });
  const AudioContextMock = class AudioContextMock {
    constructor(){
      this.state = 'running';
      this.sampleRate = 48000;
      this.destination = {};
    }
    createOscillator(){ return { type: 'sine', frequency: { value: 440 }, connect(){}, start(){}, stop(){} }; }
    createAnalyser(){ return { fftSize: 2048, frequencyBinCount: 1024, connect(){}, disconnect(){}, getFloatFrequencyData(){}, getByteFrequencyData(){} }; }
    createGain(){ return { gain: { value: 1 }, connect(){}, disconnect(){} }; }
    createBuffer(channels, length){ return { numberOfChannels: channels, length, sampleRate: 48000, getChannelData(){ return new Float32Array(length || 0); } }; }
    createBufferSource(){ return { buffer: null, connect(){}, start(){}, stop(){} }; }
    resume(){ return Promise.resolve(); }
    suspend(){ return Promise.resolve(); }
    close(){ this.state = 'closed'; return Promise.resolve(); }
  };
  const makeListenerHub = () => {
    const listeners = new Map();
    const add = (type, fn) => {
      const key = String(type || '').toLowerCase();
      if (!key || typeof fn !== 'function') return;
      if (!listeners.has(key)) listeners.set(key, new Set());
      listeners.get(key).add(fn);
    };
    const remove = (type, fn) => {
      const key = String(type || '').toLowerCase();
      if (!listeners.has(key)) return;
      listeners.get(key).delete(fn);
    };
    const dispatch = (type, event) => {
      const key = String(type || '').toLowerCase();
      const bucket = listeners.get(key);
      if (!bucket) return;
      for (const fn of Array.from(bucket)) {
        try { fn(event); } catch (_) {}
      }
    };
    return { add, remove, dispatch };
  };
  const windowEvents = makeListenerHub();

  const triggerCapture = (kind, url, headers, body) => {
    const bodyText = String(body == null ? '' : body);
    capture.clientReportBody = bodyText;
    capture.clientReportUrl = String(url || '');
    capture.clientReportHeaders = headers && typeof headers === 'object' ? Object.assign({}, headers) : {};
    if (!captureDone && typeof resolveCapture === 'function' && bodyText.trim()) {
      captureDone = true;
      try {
        resolveCapture({ kind, url: capture.clientReportUrl, body: bodyText });
      } catch (_) {}
    }
  };

  function StorageMock(initialData){
    this._map = new Map();
    if (initialData && typeof initialData === 'object') {
      for (const [key, value] of Object.entries(initialData)) {
        this._map.set(String(key), String(value));
      }
    }
  }
  StorageMock.prototype.getItem = function(k){
    const key = String(k);
    pushLog({ api: 'storage', method: 'GET', url: key });
    return this._map.has(key) ? this._map.get(key) : null;
  };
  StorageMock.prototype.setItem = function(k,v){
    const key = String(k);
    pushLog({ api: 'storage', method: 'SET', url: key, body_len: String(v == null ? '' : v).length });
    this._map.set(key, String(v));
  };
  StorageMock.prototype.removeItem = function(k){
    const key = String(k);
    pushLog({ api: 'storage', method: 'DEL', url: key });
    this._map.delete(key);
  };
  StorageMock.prototype.clear = function(){
    pushLog({ api: 'storage', method: 'CLEAR', url: 'all' });
    this._map.clear();
  };
  Object.defineProperty(StorageMock.prototype, 'length', { get(){ return this._map.size; } });

  function mkIDBRequest(resultValue, fail){
    const req = { result: resultValue, error: fail ? new Error('idb_error') : null, onsuccess: null, onerror: null, onupgradeneeded: null };
    setTimeout(() => {
      if (fail) {
        if (typeof req.onerror === 'function') { try { req.onerror({ target: req }); } catch (_) {} }
        return;
      }
      if (typeof req.onupgradeneeded === 'function') { try { req.onupgradeneeded({ target: req }); } catch (_) {} }
      if (typeof req.onsuccess === 'function') { try { req.onsuccess({ target: req }); } catch (_) {} }
    }, 0);
    return req;
  }

  function mkIndexedDB(){
    const dbRegistry = new Map();
    const ensureDb = (name) => {
      const key = String(name || 'default');
      if (!dbRegistry.has(key)) {
        dbRegistry.set(key, { name: key, stores: new Map() });
      }
      return dbRegistry.get(key);
    };
    const ensureStore = (dbEntry, storeName) => {
      const key = String(storeName || 'default');
      if (!dbEntry.stores.has(key)) dbEntry.stores.set(key, new Map());
      return dbEntry.stores.get(key);
    };
    return {
      open(name){
        const dbEntry = ensureDb(name);
        return mkIDBRequest({
          name: dbEntry.name,
          close(){},
          createObjectStore(storeName){
            const store = ensureStore(dbEntry, storeName);
            return {
              get(key){ return mkIDBRequest(store.get(JSON.stringify(key)), false); },
              put(value, key){ store.set(JSON.stringify(key), value); return mkIDBRequest(undefined, false); },
              delete(key){ store.delete(JSON.stringify(key)); return mkIDBRequest(undefined, false); },
              getAll(){ return mkIDBRequest(Array.from(store.values()), false); },
            };
          },
          transaction(storeName){
            const store = ensureStore(dbEntry, storeName);
            return {
              objectStore(){
                return {
                  get(key){ return mkIDBRequest(store.get(JSON.stringify(key)), false); },
                  put(value, key){ store.set(JSON.stringify(key), value); return mkIDBRequest(undefined, false); },
                  delete(key){ store.delete(JSON.stringify(key)); return mkIDBRequest(undefined, false); },
                  getAll(){ return mkIDBRequest(Array.from(store.values()), false); },
                };
              },
            };
          },
        }, false);
      },
      deleteDatabase(){ return mkIDBRequest(undefined, false); },
      databases: async () => [],
    };
  }

  function mkStyle(initialData){
    const state = new Map();
    const toCssName = (name) => String(name || '').replace(/[A-Z]/g, (ch) => `-${ch.toLowerCase()}`);
    const toJsName = (name) => String(name || '').replace(/-([a-z])/g, (_m, ch) => ch.toUpperCase());
    const style = {
      setProperty(name, value){
        const cssName = toCssName(name).trim();
        if (!cssName) return;
        const text = String(value == null ? '' : value);
        state.set(cssName, text);
        this[cssName] = text;
        this[toJsName(cssName)] = text;
      },
      getPropertyValue(name){
        const cssName = toCssName(name).trim();
        return state.has(cssName) ? state.get(cssName) : '';
      },
      removeProperty(name){
        const cssName = toCssName(name).trim();
        const prev = state.has(cssName) ? state.get(cssName) : '';
        state.delete(cssName);
        delete this[cssName];
        delete this[toJsName(cssName)];
        return prev;
      },
      getPropertyPriority(){ return ''; },
      item(index){ return Array.from(state.keys())[Number(index) || 0] || ''; },
      toString(){ return this.cssText; },
    };
    Object.defineProperty(style, 'length', {
      get(){ return state.size; },
    });
    Object.defineProperty(style, 'cssText', {
      get(){
        return Array.from(state.entries()).map(([key, value]) => `${key}: ${value};`).join(' ');
      },
      set(text){
        state.clear();
        const raw = String(text || '');
        for (const chunk of raw.split(';')) {
          const part = String(chunk || '').trim();
          if (!part) continue;
          const idx = part.indexOf(':');
          if (idx <= 0) continue;
          this.setProperty(part.slice(0, idx).trim(), part.slice(idx + 1).trim());
        }
      },
    });
    const seed = Object.assign({
      display: 'block',
      position: 'static',
      visibility: 'visible',
      opacity: '1',
      color: 'rgb(0, 0, 0)',
      background: 'rgba(0, 0, 0, 0)',
      'background-color': 'rgba(0, 0, 0, 0)',
      'font-size': '16px',
      'font-family': 'Arial',
      transform: 'none',
      content: 'normal',
      width: '0px',
      height: '0px',
      margin: '0px',
      padding: '0px',
      border: '0px none rgb(0, 0, 0)',
    }, initialData && typeof initialData === 'object' ? initialData : {});
    for (const [key, value] of Object.entries(seed)) {
      style.setProperty(key, value);
    }
    return style;
  }

  function CanvasRenderingContext2DMock(){}
  CanvasRenderingContext2DMock.prototype.getImageData = nativeFn('getImageData', function getImageData(_x, _y, w, h){
    return {
      data: new Uint8ClampedArray([12, 34, 56, 255, 78, 90, 123, 255, 45, 67, 89, 255, 210, 180, 140, 255]),
      width: Number(w || 2) || 2,
      height: Number(h || 2) || 2,
    };
  });
  CanvasRenderingContext2DMock.prototype.fillRect = nativeFn('fillRect', function fillRect(){});
  CanvasRenderingContext2DMock.prototype.drawImage = nativeFn('drawImage', function drawImage(){});
  CanvasRenderingContext2DMock.prototype.fillText = nativeFn('fillText', function fillText(){});
  CanvasRenderingContext2DMock.prototype.createLinearGradient = nativeFn('createLinearGradient', function createLinearGradient(){
    return { addColorStop(){}, toString(){ return '[object CanvasGradient]'; } };
  });
  CanvasRenderingContext2DMock.prototype.createRadialGradient = nativeFn('createRadialGradient', function createRadialGradient(){
    return { addColorStop(){}, toString(){ return '[object CanvasGradient]'; } };
  });
  CanvasRenderingContext2DMock.prototype.createPattern = nativeFn('createPattern', function createPattern(){ return null; });
  CanvasRenderingContext2DMock.prototype.beginPath = nativeFn('beginPath', function beginPath(){});
  CanvasRenderingContext2DMock.prototype.closePath = nativeFn('closePath', function closePath(){});
  CanvasRenderingContext2DMock.prototype.stroke = nativeFn('stroke', function stroke(){});
  CanvasRenderingContext2DMock.prototype.fill = nativeFn('fill', function fill(){});
  CanvasRenderingContext2DMock.prototype.clearRect = nativeFn('clearRect', function clearRect(){});
  CanvasRenderingContext2DMock.prototype.strokeRect = nativeFn('strokeRect', function strokeRect(){});
  CanvasRenderingContext2DMock.prototype.moveTo = nativeFn('moveTo', function moveTo(){});
  CanvasRenderingContext2DMock.prototype.lineTo = nativeFn('lineTo', function lineTo(){});
  CanvasRenderingContext2DMock.prototype.arc = nativeFn('arc', function arc(){});
  CanvasRenderingContext2DMock.prototype.ellipse = nativeFn('ellipse', function ellipse(){});
  CanvasRenderingContext2DMock.prototype.rect = nativeFn('rect', function rect(){});
  CanvasRenderingContext2DMock.prototype.translate = nativeFn('translate', function translate(){});
  CanvasRenderingContext2DMock.prototype.rotate = nativeFn('rotate', function rotate(){});
  CanvasRenderingContext2DMock.prototype.scale = nativeFn('scale', function scale(){});
  CanvasRenderingContext2DMock.prototype.transform = nativeFn('transform', function transform(){});
  CanvasRenderingContext2DMock.prototype.setTransform = nativeFn('setTransform', function setTransform(){});
  CanvasRenderingContext2DMock.prototype.clip = nativeFn('clip', function clip(){});
  CanvasRenderingContext2DMock.prototype.strokeText = nativeFn('strokeText', function strokeText(){});
  CanvasRenderingContext2DMock.prototype.putImageData = nativeFn('putImageData', function putImageData(){});
  CanvasRenderingContext2DMock.prototype.isPointInPath = nativeFn('isPointInPath', function isPointInPath(){ return false; });
  CanvasRenderingContext2DMock.prototype.isPointInStroke = nativeFn('isPointInStroke', function isPointInStroke(){ return false; });
  CanvasRenderingContext2DMock.prototype.save = nativeFn('save', function save(){});
  CanvasRenderingContext2DMock.prototype.restore = nativeFn('restore', function restore(){});
  CanvasRenderingContext2DMock.prototype.setLineDash = nativeFn('setLineDash', function setLineDash(){});
  CanvasRenderingContext2DMock.prototype.getLineDash = nativeFn('getLineDash', function getLineDash(){ return []; });
  CanvasRenderingContext2DMock.prototype.measureText = nativeFn('measureText', function measureText(text){
    return {
      width: String(text || '').length * 7.12,
      actualBoundingBoxLeft: 0,
      actualBoundingBoxRight: 0,
      actualBoundingBoxAscent: 10,
      actualBoundingBoxDescent: 2,
    };
  });

  function HTMLCanvasElementMock(){}
  HTMLCanvasElementMock.prototype.toDataURL = nativeFn('toDataURL', function toDataURL(){
    const raw = Buffer.from('canvas:seed', 'utf8').toString('base64');
    return `data:image/png;base64,${raw}`;
  });
  function WebGLRenderingContextMock(){}
  function WebGL2RenderingContextMock(){}
  const createWebGLContext = (canvas) => {
    const extensions = ['EXT_texture_filter_anisotropic', 'OES_element_index_uint', 'WEBGL_debug_renderer_info'];
    const shaderPrecision = { rangeMin: 127, rangeMax: 127, precision: 23 };
    return {
      canvas,
      drawingBufferWidth: 300,
      drawingBufferHeight: 150,
      getParameter(param){
        const map = new Map([
          [37445, 'Google Inc. (Intel)'],
          [37446, 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)'],
          [7936, 'WebKit'],
          [7937, 'WebKit WebGL'],
          [7938, 'WebGL 1.0'],
          [33901, 16],
          [34024, 16384],
          [34921, 16],
          [35661, 16],
        ]);
        return map.has(param) ? map.get(param) : 0;
      },
      getExtension(name){
        const key = String(name || '');
        if (key === 'WEBGL_debug_renderer_info') {
          return { UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446 };
        }
        if (extensions.includes(key)) return { name: key };
        return null;
      },
      getSupportedExtensions(){ return extensions.slice(); },
      getContextAttributes(){ return { alpha: true, antialias: true, depth: true, stencil: false, premultipliedAlpha: true, preserveDrawingBuffer: false }; },
      getShaderPrecisionFormat(){ return Object.assign({}, shaderPrecision); },
      createProgram(){ return {}; },
      createShader(type){ return { type }; },
      shaderSource(){},
      compileShader(){},
      getShaderParameter(){ return true; },
      getShaderInfoLog(){ return ''; },
      attachShader(){},
      linkProgram(){},
      getProgramParameter(){ return true; },
      getProgramInfoLog(){ return ''; },
      useProgram(){},
      createBuffer(){ return {}; },
      bindBuffer(){},
      bufferData(){},
      vertexAttribPointer(){},
      enableVertexAttribArray(){},
      createTexture(){ return {}; },
      bindTexture(){},
      texImage2D(){},
      texParameteri(){},
      createFramebuffer(){ return {}; },
      bindFramebuffer(){},
      framebufferTexture2D(){},
      checkFramebufferStatus(){ return 36053; },
      createRenderbuffer(){ return {}; },
      bindRenderbuffer(){},
      renderbufferStorage(){},
      framebufferRenderbuffer(){},
      createImageData(){ return { data: new Uint8ClampedArray(4), width: 1, height: 1 }; },
      clearColor(){},
      clear(){},
      viewport(){},
      getUniformLocation(){ return {}; },
      uniform1f(){},
      drawArrays(){},
      readPixels(_x, _y, _w, _h, _fmt, _type, pixels){
        if (pixels && typeof pixels.length === 'number') {
          for (let i = 0; i < pixels.length; i++) pixels[i] = i % 255;
        }
      },
      getAttribLocation(){ return 0; },
      activeTexture(){},
      pixelStorei(){},
      blendFunc(){},
      enable(){},
      disable(){},
      scissor(){},
      flush(){},
      finish(){},
      getError(){ return 0; },
      deleteShader(){},
      deleteProgram(){},
      deleteBuffer(){},
      deleteTexture(){},
    };
  };

  let ctx = null;
  const cookieJar = new Map();
  const webSqlStore = new Map();
  const serializeCookieJar = () => Array.from(cookieJar.entries()).map(([name, value]) => `${name}=${value}`).join('; ');
  const applyDocumentCookieSet = (rawValue) => {
    const text = String(rawValue || '').trim();
    if (!text) return serializeCookieJar();
    const first = text.split(';', 1)[0] || '';
    const eq = first.indexOf('=');
    if (eq > 0) {
      const name = first.slice(0, eq).trim();
      const value = first.slice(eq + 1).trim();
      if (name) cookieJar.set(name, value);
    }
    return serializeCookieJar();
  };
  const summarizeElement = (el) => ({
    tagName: String((el && el.tagName) || ''),
    src: String((el && el.src) || ''),
    href: String((el && el.href) || ''),
  });
  const scheduleLoad = (fn) => {
    if (typeof fn !== 'function') return;
    setTimeout(() => {
      try { fn(); } catch (_) {}
    }, 0);
  };
  const applyGeeProfilePatch = (h, o, f) => {
    if (!profilePatch || !h || typeof h !== 'object') return;
    if (profilePatch.env && typeof profilePatch.env === 'object') {
      const envCopy = cloneJson(profilePatch.env);
      h.env = envCopy;
      if (o && typeof o === 'object') {
        for (const key of Object.keys(o)) delete o[key];
        Object.assign(o, cloneJson(profilePatch.env));
      }
    }
    if (profilePatch.du && typeof profilePatch.du === 'object') {
      const duCopy = cloneJson(profilePatch.du);
      h.du = duCopy;
      if (f && typeof f === 'object') {
        for (const key of Object.keys(f)) delete f[key];
        Object.assign(f, cloneJson(profilePatch.du));
      }
    }
    if (profilePatch.tu && typeof profilePatch.tu === 'object') {
      h.tu = cloneJson(profilePatch.tu);
    }
    if (profilePatch.force_sign_empty) h.sign = '';
    if (profilePatch.force_ct !== undefined) h.ct = String(profilePatch.force_ct);
    if (profilePatch.delete_uid) delete h.uid;
  };
  const runScriptInWindow = (targetWindow, source, opts = {}) => {
    const code = String(source || '');
    if (!code.trim()) return;
    try {
      pushLog({
        api: opts.api || 'script_inline',
        method: opts.method || 'EVAL',
        url: String(opts.url || ''),
        body_len: code.length,
      });
      vm.runInContext(code, targetWindow);
    } catch (err) {
      pushLog({
        api: opts.api || 'script_inline_error',
        method: opts.method || 'EVAL',
        url: String(opts.url || ''),
        error: String(err && err.stack ? err.stack : err),
      });
    }
  };
  const runHtmlInWindow = (targetWindow, htmlText, opts = {}) => {
    const html = String(htmlText || '');
    if (!html.trim()) return;
    const scriptTagRe = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
    let match = null;
    while ((match = scriptTagRe.exec(html))) {
      const attrs = String(match[1] || '');
      const inlineCode = String(match[2] || '');
      const srcMatch = attrs.match(/\bsrc=["']([^"']+)["']/i);
      if (srcMatch && srcMatch[1]) {
        const src = String(srcMatch[1] || '').trim();
        pushLog({
          api: opts.api || 'iframe_script',
          method: 'SRC',
          url: src,
        });
        if (src.toLowerCase().includes('geeguard') && src.toLowerCase().includes('.js')) {
          runScriptInWindow(targetWindow, geeguardJs, {
            api: opts.api || 'iframe_script',
            method: 'EVAL',
            url: src,
          });
        }
        continue;
      }
      runScriptInWindow(targetWindow, inlineCode, {
        api: opts.api || 'iframe_script',
        method: 'INLINE',
        url: String(opts.url || ''),
      });
    }
  };
  const loadScriptIntoWindow = (targetWindow, el, containerName) => {
    const src = String((el && el.src) || '');
    const inlineCode = String((el && (el.text || el.textContent || el.innerHTML)) || '');
    pushLog({
      api: containerName || 'script_append',
      method: 'APPEND',
      url: src || String((el && el.tagName) || ''),
      body_len: inlineCode.length,
    });
    try {
      if (src.includes('/g2/api/v1/pre_load')) {
        const cbName = new URL(src).searchParams.get('callback');
        if (cbName && targetWindow && typeof targetWindow[cbName] === 'function') {
          targetWindow[cbName](prePayload);
        }
        scheduleLoad(el && el.onload);
        return el;
      }
      if (src.toLowerCase().includes('geeguard') && src.toLowerCase().includes('.js')) {
        runScriptInWindow(targetWindow, geeguardJs, {
          api: containerName || 'script_append',
          method: 'EVAL',
          url: src,
        });
        scheduleLoad(el && el.onload);
        return el;
      }
      if (!src) {
        runScriptInWindow(targetWindow, inlineCode, {
          api: containerName || 'script_append',
          method: 'INLINE',
          url: '',
        });
        scheduleLoad(el && el.onload);
        return el;
      }
    } catch (err) {
      pushLog({
        api: `${containerName || 'script_append'}_error`,
        method: 'EVAL',
        url: src,
        error: String(err && err.stack ? err.stack : err),
      });
      if (typeof (el && el.onerror) === 'function') {
        try { el.onerror(err); } catch (_) {}
      }
      return el;
    }
    if (typeof (el && el.onerror) === 'function') {
      try { el.onerror(new Error('unsupported script src')); } catch (_) {}
    }
    return el;
  };
  const makeElement = (tagName) => {
    const tag = String(tagName || '').toLowerCase();
    let currentSrc = '';
    let currentHref = '';
    let currentOnload = null;
    let currentOnerror = null;
    const loadListeners = new Set();
    const errorListeners = new Set();
    const el = {
      tagName: tag.toUpperCase(),
      style: mkStyle(),
      _isConnected: false,
      _loadReady: false,
      rel: '',
      async: true,
      onreadystatechange: null,
      readyState: '',
      text: '',
      textContent: '',
      innerHTML: '',
      srcdoc: '',
      id: '',
      className: '',
      children: [],
      childNodes: [],
      ownerDocument: null,
      parentNode: null,
      _fireLoad(){
        this._loadReady = true;
        if (typeof currentOnload === 'function') scheduleLoad(currentOnload);
        for (const fn of Array.from(loadListeners)) scheduleLoad(fn);
      },
      _fireError(err){
        if (typeof currentOnerror === 'function') {
          scheduleLoad(() => currentOnerror(err));
        }
        for (const fn of Array.from(errorListeners)) {
          scheduleLoad(() => fn(err));
        }
      },
      setAttribute(k, v){
        const key = String(k);
        const value = String(v);
        this[key] = value;
      },
      getAttribute(k){ return this[String(k)] || null; },
      addEventListener(type, fn){
        const t = String(type || '').toLowerCase();
        if (t === 'load' && typeof fn === 'function') {
          loadListeners.add(fn);
          if (this._loadReady) scheduleLoad(fn);
        }
        if (t === 'error' && typeof fn === 'function') errorListeners.add(fn);
      },
      removeEventListener(){},
      appendChild(child){
        if (child && typeof child === 'object') {
          child.parentNode = this;
          child._isConnected = true;
          this.children.push(child);
          this.childNodes.push(child);
        }
        pushLog({ api: 'dom_append', method: 'APPEND', url: `${this.tagName}:${String((child && child.tagName) || '')}` });
        if (child && String(child.tagName || '').toLowerCase() === 'script') {
          const targetWindow = (child.ownerDocument && child.ownerDocument.defaultView) || ctx;
          return loadScriptIntoWindow(targetWindow, child, `${this.tagName.toLowerCase()}_script`);
        }
        if (child && typeof child._fireLoad === 'function') {
          scheduleLoad(() => child._fireLoad());
        } else {
          scheduleLoad(child && child.onload);
        }
        return child;
      },
      insertBefore(child){
        return this.appendChild(child);
      },
      removeChild(child){
        this.children = this.children.filter((item) => item !== child);
        this.childNodes = this.childNodes.filter((item) => item !== child);
      },
      append(...children){
        let last = null;
        for (const child of children) last = this.appendChild(child);
        return last;
      },
      querySelector(){ return null; },
      querySelectorAll(){ return []; },
      getBoundingClientRect(){ return { x: 0, y: 0, top: 0, left: 0, width: 1, height: 1, right: 1, bottom: 1 }; },
    };
    Object.defineProperty(el, 'offsetWidth', { get(){ return parseInt(String(el.style.width || '120'), 10) || 120; } });
    Object.defineProperty(el, 'offsetHeight', { get(){ return parseInt(String(el.style.height || '24'), 10) || 24; } });
    Object.defineProperty(el, 'clientWidth', { get(){ return parseInt(String(el.style.width || '120'), 10) || 120; } });
    Object.defineProperty(el, 'clientHeight', { get(){ return parseInt(String(el.style.height || '24'), 10) || 24; } });
    Object.defineProperty(el, 'scrollWidth', { get(){ return el.clientWidth; } });
    Object.defineProperty(el, 'scrollHeight', { get(){ return el.clientHeight; } });
    Object.defineProperty(el, 'src', {
      get(){ return currentSrc; },
      set(v){
        currentSrc = String(v || '');
        if (tag === 'iframe' && el._isConnected) {
          scheduleLoad(() => el._fireLoad());
        }
      },
      configurable: true,
      enumerable: true,
    });
    Object.defineProperty(el, 'href', {
      get(){ return currentHref; },
      set(v){ currentHref = String(v || ''); },
      configurable: true,
      enumerable: true,
    });
    Object.defineProperty(el, 'onload', {
      get(){ return currentOnload; },
      set(fn){
        currentOnload = typeof fn === 'function' ? fn : null;
        if (el._loadReady && currentOnload) scheduleLoad(currentOnload);
      },
      configurable: true,
      enumerable: true,
    });
    Object.defineProperty(el, 'onerror', {
      get(){ return currentOnerror; },
      set(fn){ currentOnerror = typeof fn === 'function' ? fn : null; },
      configurable: true,
      enumerable: true,
    });
    if (tag === 'canvas') {
      Object.setPrototypeOf(el, HTMLCanvasElementMock.prototype);
      el.width = 300;
      el.height = 150;
      el.getContext = nativeFn('getContext', function getContext(kind){
        const mode = String(kind || '').toLowerCase();
        if (mode === 'webgl' || mode === 'experimental-webgl' || mode === 'webgl2') {
          const glCtx = createWebGLContext(el);
          Object.setPrototypeOf(glCtx, (mode === 'webgl2' ? WebGL2RenderingContextMock : WebGLRenderingContextMock).prototype);
          return glCtx;
        }
        if (mode !== '2d') return null;
        const ctx2d = new CanvasRenderingContext2DMock();
        ctx2d.canvas = el;
        ctx2d.fillStyle = '#000000';
        return ctx2d;
      });
    }
    if (tag === 'iframe') {
      const iframeEvents = makeListenerHub();
      let iframeHtmlBuffer = '';
      const iframeWindow = Object.create(ctx || null);
      const iframeDocument = Object.create(documentMock);
      const iframeHead = {
        appendChild(child){
          if (child && typeof child === 'object') child.parentNode = this;
          if (child && String(child.tagName || '').toLowerCase() === 'script') {
            return loadScriptIntoWindow(iframeWindow, child, 'iframe_head');
          }
          scheduleLoad(child && child.onload);
          return child;
        },
        removeChild(){},
        append(...children){
          let last = null;
          for (const child of children) last = this.appendChild(child);
          return last;
        },
      };
      const iframeBody = {
        style: mkStyle(),
        children: [],
        childNodes: [],
        appendChild(child){
          if (child && typeof child === 'object') {
            child.parentNode = this;
            this.children.push(child);
            this.childNodes.push(child);
          }
          pushLog({ api: 'iframe_body', method: 'APPEND', url: JSON.stringify(summarizeElement(child)) });
          if (child && String(child.tagName || '').toLowerCase() === 'script') {
            return loadScriptIntoWindow(iframeWindow, child, 'iframe_body_script');
          }
          scheduleLoad(child && child.onload);
          return child;
        },
        removeChild(){},
        insertBefore(child){
          return this.appendChild(child);
        },
        append(...children){
          let last = null;
          for (const child of children) last = this.appendChild(child);
          return last;
        },
      };
      iframeDocument.body = iframeBody;
      iframeDocument.head = iframeHead;
      iframeDocument.documentElement = {
        clientWidth: ctx ? ctx.innerWidth : 1366,
        clientHeight: ctx ? ctx.innerHeight : 768,
        style: mkStyle(),
        children: [],
        childNodes: [],
        appendChild(child){
          if (child && typeof child === 'object') {
            child.parentNode = this;
            this.children.push(child);
            this.childNodes.push(child);
          }
          pushLog({ api: 'iframe_document_element', method: 'APPEND', url: JSON.stringify(summarizeElement(child)) });
          if (child && String(child.tagName || '').toLowerCase() === 'script') {
            return loadScriptIntoWindow(iframeWindow, child, 'iframe_document_element_script');
          }
          if (child && typeof child._fireLoad === 'function') {
            scheduleLoad(() => child._fireLoad());
          } else {
            scheduleLoad(child && child.onload);
          }
          return child;
        },
        insertBefore(child){
          return this.appendChild(child);
        },
        removeChild(){},
        append(...children){
          let last = null;
          for (const child of children) last = this.appendChild(child);
          return last;
        },
        querySelector(){ return null; },
        querySelectorAll(){ return []; },
      };
      iframeDocument.referrer = parsedTarget.origin + '/';
      iframeDocument.URL = parsedTarget.href;
      iframeDocument.documentURI = parsedTarget.href;
      iframeDocument.baseURI = parsedTarget.href;
      iframeDocument.createElement = (name) => {
        const child = makeElement(name);
        child.ownerDocument = iframeDocument;
        return child;
      };
      iframeDocument.getElementsByTagName = (name) => {
        const lower = String(name || '').toLowerCase();
        if (lower === 'head') return [iframeHead];
        if (lower === 'body') return [iframeBody];
        if (lower === 'html') return [iframeDocument.documentElement];
        return [];
      };
      iframeDocument.querySelector = (selector) => {
        const lower = String(selector || '').toLowerCase().trim();
        if (lower === 'head') return iframeHead;
        if (lower === 'body') return iframeBody;
        if (lower === 'html') return iframeDocument.documentElement;
        return null;
      };
      iframeDocument.open = () => {
        iframeHtmlBuffer = '';
      };
      iframeDocument.write = (...chunks) => {
        const piece = chunks.map((item) => String(item == null ? '' : item)).join('');
        iframeHtmlBuffer += piece;
        pushLog({ api: 'iframe_write', method: 'WRITE', url: '', body_len: piece.length });
      };
      iframeDocument.close = () => {
        pushLog({ api: 'iframe_write', method: 'CLOSE', url: '', body_len: iframeHtmlBuffer.length });
        runHtmlInWindow(iframeWindow, iframeHtmlBuffer, { api: 'iframe_write' });
      };
      iframeDocument.addEventListener = (type, fn) => {
        const t = String(type || '').toLowerCase();
        if ((t === 'load' || t === 'domcontentloaded' || t === 'readystatechange') && typeof fn === 'function') {
          scheduleLoad(fn);
        }
      };
      iframeDocument.removeEventListener = () => {};
      iframeHead.parentNode = iframeDocument.documentElement;
      iframeBody.parentNode = iframeDocument.documentElement;
      iframeDocument.documentElement.children.push(iframeHead, iframeBody);
      iframeDocument.documentElement.childNodes.push(iframeHead, iframeBody);
      Object.defineProperty(iframeDocument, 'cookie', {
        get(){ return serializeCookieJar(); },
        set(value){ return applyDocumentCookieSet(value); },
      });
      iframeWindow.document = iframeDocument;
      iframeWindow.navigator = Object.assign({}, ctx ? ctx.navigator : {}, { userAgent });
      iframeWindow.location = { href: 'about:blank', origin: parsedTarget.origin, protocol: parsedTarget.protocol, host: parsedTarget.host, hostname: parsedTarget.hostname };
      iframeWindow.name = '';
      iframeWindow.addEventListener = (type, fn) => { iframeEvents.add(type, fn); };
      iframeWindow.removeEventListener = (type, fn) => { iframeEvents.remove(type, fn); };
      iframeWindow.dispatchEvent = (event) => {
        const type = String((event && event.type) || '').toLowerCase();
        iframeEvents.dispatch(type, event);
        return true;
      };
      iframeWindow.postMessage = (data, origin) => {
        windowEvents.dispatch('message', {
          type: 'message',
          data,
          origin: String(origin || parsedTarget.origin || ''),
          source: iframeWindow,
        });
      };
      iframeWindow.matchMedia = () => ({ matches: false, media: '', onchange: null, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}, dispatchEvent(){ return false; } });
      iframeWindow.frameElement = el;
      iframeWindow.parent = null;
      iframeWindow.top = null;
      iframeWindow.self = null;
      iframeWindow.window = iframeWindow;
      iframeWindow.globalThis = iframeWindow;
      iframeWindow.global = iframeWindow;
      iframeWindow.document.defaultView = iframeWindow;
      iframeWindow.parent = ctx;
      iframeWindow.top = ctx;
      iframeWindow.self = iframeWindow;
      el.contentWindow = iframeWindow;
      el.contentDocument = iframeDocument;
    }
    el.ownerDocument = documentMock;
    return el;
  };
  const headEl = {
    appendChild(el){
      if (el && typeof el === 'object') el.parentNode = this;
      if (el && String(el.tagName || '').toLowerCase() === 'script') {
        return loadScriptIntoWindow(ctx, el, 'head_append');
      }
      pushLog({ api: 'head_append', method: 'APPEND', url: String((el && el.tagName) || '') });
      scheduleLoad(el && el.onload);
      return el;
    },
    removeChild(){},
  };

  const documentMock = {
    hidden: false,
    visibilityState: 'visible',
    readyState: 'complete',
    referrer: parsedTarget.origin + '/',
    title: '',
    URL: parsedTarget.href,
    documentURI: parsedTarget.href,
    baseURI: parsedTarget.href,
    characterSet: 'UTF-8',
    charset: 'UTF-8',
    compatMode: 'CSS1Compat',
    head: headEl,
    documentElement: {
      clientWidth: isAndroid ? 412 : 1366,
      clientHeight: isAndroid ? 915 : 768,
      style: mkStyle(),
      children: [],
      childNodes: [],
      querySelector(){ return null; },
      querySelectorAll(){ return []; },
      appendChild(el){
        if (el && typeof el === 'object') {
          el.parentNode = this;
          this.children.push(el);
          this.childNodes.push(el);
        }
        pushLog({ api: 'document_element', method: 'APPEND', url: JSON.stringify(summarizeElement(el)) });
        if (el && String(el.tagName || '').toLowerCase() === 'script') {
          return loadScriptIntoWindow(ctx, el, 'document_element_script');
        }
        if (el && typeof el._fireLoad === 'function') {
          scheduleLoad(() => el._fireLoad());
        } else {
          scheduleLoad(el && el.onload);
        }
        return el;
      },
      insertBefore(el){
        return this.appendChild(el);
      },
      removeChild(){},
      append(...children){
        let last = null;
        for (const child of children) last = this.appendChild(child);
        return last;
      },
      querySelector(){ return null; },
      querySelectorAll(){ return []; },
    },
    body: {
      appendChild(el){
        if (el && typeof el === 'object') {
          el.parentNode = this;
          if (!Array.isArray(this.children)) this.children = [];
          if (!Array.isArray(this.childNodes)) this.childNodes = [];
          this.children.push(el);
          this.childNodes.push(el);
        }
        pushLog({ api: 'body_append', method: 'APPEND', url: JSON.stringify(summarizeElement(el)) });
        if (el && String(el.tagName || '').toLowerCase() === 'script') {
          return loadScriptIntoWindow(ctx, el, 'body_script');
        }
        if (typeof (el && el.onload) === 'function') {
          scheduleLoad(el.onload);
        }
        return el;
      },
      removeChild(){},
      insertBefore(el){
        if (typeof (el && el.onload) === 'function') {
          setTimeout(() => { try { el.onload(); } catch (_) {} }, 0);
        }
        return el;
      },
      append(...children){
        let last = null;
        for (const child of children) last = this.appendChild(child);
        return last;
      },
      style: mkStyle(),
      children: [],
      childNodes: [],
    },
    getElementsByTagName(name){
      const lower = String(name || '').toLowerCase();
      if (lower === 'head') return [headEl];
      if (lower === 'body') return [this.body];
      if (lower === 'html') return [this.documentElement];
      return [];
    },
    createElement(name){
      return makeElement(name);
    },
    createEvent(){ return { initEvent(){}, initCustomEvent(){}, initMouseEvent(){} }; },
    addEventListener(type, fn){
      const t = String(type || '').toLowerCase();
      if ((t === 'load' || t === 'domcontentloaded' || t === 'readystatechange') && typeof fn === 'function') {
        setTimeout(() => { try { fn(); } catch (_) {} }, 0);
      }
    },
    hasFocus(){ return true; },
    removeEventListener(){},
    querySelector(selector){
      const lower = String(selector || '').toLowerCase().trim();
      if (lower === 'head') return this.head;
      if (lower === 'body') return this.body;
      if (lower === 'html') return this.documentElement;
      return null;
    },
    querySelectorAll(){ return []; },
    execCommand(){ return false; },
    queryCommandSupported(){ return false; },
    queryCommandEnabled(){ return false; },
    queryCommandState(){ return false; },
    queryCommandValue(){ return ''; },
  };
  headEl.parentNode = documentMock.documentElement;
  documentMock.body.parentNode = documentMock.documentElement;
  documentMock.documentElement.children.push(headEl, documentMock.body);
  documentMock.documentElement.childNodes.push(headEl, documentMock.body);
  Object.defineProperty(documentMock, 'cookie', {
    get(){ return serializeCookieJar(); },
    set(value){ return applyDocumentCookieSet(value); },
  });

  class XhrMock {
    constructor(){
      this._headers = {};
      this.status = 0;
      this.readyState = 0;
      this.responseText = '';
      this.onreadystatechange = null;
      this.onload = null;
      this.onerror = null;
    }
    open(method, url){
      this._method = String(method || 'GET').toUpperCase();
      this._url = String(url || '');
      this.readyState = 1;
    }
    setRequestHeader(name, value){
      this._headers[String(name)] = String(value);
    }
    send(body){
      const bodyText = String(body || '');
      const reqUrl = String(this._url || '');
      pushLog({ api: 'xhr', method: this._method || 'GET', url: reqUrl, body_len: bodyText.length });
      if (reqUrl.toLowerCase().includes('riskct.geetest.com') && reqUrl.toLowerCase().includes('client_report')) {
        triggerCapture('xhr', reqUrl, this._headers, bodyText);
      }
      this.status = 200;
      this.readyState = 4;
      this.responseText = JSON.stringify({ status: 'success', code: 0, data: { gee_token: 'RzA_mock' } });
      if (typeof this.onreadystatechange === 'function') { try { this.onreadystatechange(); } catch (_) {} }
      if (typeof this.onload === 'function') { try { this.onload(); } catch (_) {} }
    }
  }
  function ImageMock(){
    this.onload = null;
    this.onerror = null;
    let _src = '';
    Object.defineProperty(this, 'src', {
      get(){ return _src; },
      set(v){
        _src = String(v || '');
        pushLog({ api: 'image', method: 'GET', url: _src });
        if (typeof this.onload === 'function') { try { this.onload(); } catch (_) {} }
      },
    });
  }

  ctx = {
    console: consoleShim,
    Math, Date, JSON, Object, Array, String, Number, Boolean, RegExp, Error, Promise,
    URL, URLSearchParams, encodeURIComponent, decodeURIComponent,
    setTimeout, clearTimeout, setInterval: safeSetInterval, clearInterval,
    setImmediate: (...args) => setTimeout(...args),
    clearImmediate: (id) => clearTimeout(id),
    queueMicrotask: globalThis.queueMicrotask || ((fn) => Promise.resolve().then(fn)),
    requestAnimationFrame: (cb) => setTimeout(() => cb(Date.now()), 16),
    cancelAnimationFrame: (id) => clearTimeout(id),
    parseInt, parseFloat, isNaN,
    Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, Int32Array,
    Float32Array, Float64Array, ArrayBuffer, DataView, Uint8ClampedArray,
    performance: { now: () => Number(process.hrtime.bigint() / 1000000n), timeOrigin: Date.now(), memory: { jsHeapSizeLimit: 4294705152, totalJSHeapSize: 12000000, usedJSHeapSize: 8000000 } },
    atob: (s) => Buffer.from(String(s || ''), 'base64').toString('binary'),
    btoa: (s) => {
      const out = Buffer.from(String(s || ''), 'binary').toString('base64');
      if (out.length >= 800 || out.startsWith('R0VFAA')) bodyCandidates.push(out);
      return out;
    },
    crypto: nodeWebCrypto,
    document: documentMock,
    location: { protocol: parsedTarget.protocol, host: parsedTarget.host, hostname: parsedTarget.hostname, href: parsedTarget.href, origin: parsedTarget.origin, pathname: parsedTarget.pathname, search: parsedTarget.search },
    name: '',
    history: { length: 1, state: null, pushState(){}, replaceState(){} },
    getComputedStyle(target){
      const style = target && target.style && typeof target.style.getPropertyValue === 'function' ? target.style : mkStyle();
      return style;
    },
    devicePixelRatio: isAndroid ? 3 : 1,
    innerWidth: isAndroid ? 412 : 1366,
    innerHeight: isAndroid ? 915 : 768,
    outerWidth: isAndroid ? 412 : 1366,
    outerHeight: isAndroid ? 915 : 768,
    isSecureContext: true,
    structuredClone: globalThis.structuredClone,
    Intl,
    TextEncoder: TextEncoderCtor,
    TextDecoder: TextDecoderCtor,
    Blob: BlobCtor,
    File: FileCtor,
    Headers: HeadersCtor,
    Request: RequestCtor,
    Response: ResponseCtor,
    FormData: FormDataCtor,
    AbortController: AbortControllerCtor,
    AbortSignal: AbortSignalCtor,
    ReadableStream: ReadableStreamCtor,
    WritableStream: WritableStreamCtor,
    TransformStream: TransformStreamCtor,
    EventTarget: EventTargetCtor,
    Event: EventCtor,
    CustomEvent: CustomEventCtor,
    DOMException: DOMExceptionCtor,
    MessageChannel: MessageChannelCtor,
    MessagePort: MessagePortCtor,
    chrome: { runtime: {}, app: {}, webstore: {} },
    CanvasRenderingContext2D: CanvasRenderingContext2DMock,
    HTMLCanvasElement: HTMLCanvasElementMock,
    WebGLRenderingContext: WebGLRenderingContextMock,
    WebGL2RenderingContext: WebGL2RenderingContextMock,
    navigator: {
      userAgent,
      language,
      languages: [language, 'pt'],
      platform: isAndroid ? 'Linux armv8l' : 'Win32',
      vendor: 'Google Inc.',
      hardwareConcurrency: 8,
      deviceMemory: 8,
      maxTouchPoints: isAndroid ? 5 : 0,
      productSub: '20030107',
      cookieEnabled: true,
      webdriver: false,
      onLine: true,
      pdfViewerEnabled: true,
      plugins: mkPluginArray(),
      mimeTypes: mkMimeTypeArray(),
      userAgentData: {
        mobile: !!isAndroid,
        platform: isAndroid ? 'Android' : 'Windows',
        brands: [
          { brand: 'Not=A?Brand', version: '8' },
          { brand: 'Chromium', version: '131' },
          { brand: 'Google Chrome', version: '131' },
        ],
        getHighEntropyValues: async () => ({
          platform: isAndroid ? 'Android' : 'Windows',
          platformVersion: isAndroid ? '14.0.0' : '10.0.0',
          architecture: isAndroid ? 'arm' : 'x86',
          model: '',
          uaFullVersion: '131.0.0.0',
        }),
      },
      connection: { effectiveType: '4g', rtt: 50, downlink: 10, saveData: false, addEventListener(){}, removeEventListener(){} },
      permissions: { query: async () => ({ state: 'prompt' }) },
      storage: {
        estimate: async () => ({ quota: 1073741824, usage: 262144 }),
        persisted: async () => true,
        persist: async () => true,
      },
      webkitTemporaryStorage: {
        queryUsageAndQuota(successCallback){
          if (typeof successCallback === 'function') {
            try { successCallback(0, 1073741824); } catch (_) {}
          }
        },
        requestQuota(_type, requestedBytes, successCallback){
          if (typeof successCallback === 'function') {
            try { successCallback(Number(requestedBytes || 1073741824) || 1073741824); } catch (_) {}
          }
        },
      },
      serviceWorker: {
        getRegistrations: async () => [],
      },
      mediaDevices: {
        enumerateDevices: async () => [],
        getUserMedia: async () => { throw new Error('NotAllowedError'); },
      },
      locks: {
        request: async (_name, cb) => (typeof cb === 'function' ? cb({ name: String(_name || '') }) : undefined),
      },
      sendBeacon(url, data){
        const reqUrl = String(url || '');
        const bodyText = String(data || '');
        pushLog({ api: 'beacon', method: 'POST', url: reqUrl, body_len: bodyText.length });
        if (reqUrl.toLowerCase().includes('riskct.geetest.com') && reqUrl.toLowerCase().includes('client_report')) {
          triggerCapture('beacon', reqUrl, {}, bodyText);
        }
        return true;
      },
    },
    screen: {
      width: isAndroid ? 412 : 1366,
      height: isAndroid ? 915 : 768,
      availWidth: isAndroid ? 412 : 1366,
      availHeight: isAndroid ? 915 : 728,
      colorDepth: 24,
      pixelDepth: 24,
      orientation: { type: isAndroid ? 'portrait-primary' : 'landscape-primary', angle: 0, addEventListener(){}, removeEventListener(){} },
    },
    visualViewport: {
      width: isAndroid ? 412 : 1366,
      height: isAndroid ? 915 : 768,
      scale: 1,
      offsetLeft: 0,
      offsetTop: 0,
      pageLeft: 0,
      pageTop: 0,
      addEventListener(){},
      removeEventListener(){},
    },
    localStorage: new StorageMock({ gt_uid: seededGtUid }),
    sessionStorage: new StorageMock({ gt_uid: seededGtUid }),
    indexedDB: mkIndexedDB(),
    caches: mkCaches(),
    Image: ImageMock,
    AudioContext: AudioContextMock,
    webkitAudioContext: AudioContextMock,
    XMLHttpRequest: XhrMock,
    openDatabase(){
      const makeRows = (value) => ({
        length: value === undefined ? 0 : 1,
        item(index){
          if (index !== 0 || value === undefined) return undefined;
          return { value };
        },
      });
      const makeResult = (value) => ({ rows: makeRows(value) });
      return {
        transaction(cb){
          if (typeof cb !== 'function') return;
          const tx = {
            executeSql(sql, params, successCallback, errorCallback){
              const rawSql = String(sql || '');
              const upperSql = rawSql.toUpperCase();
              const values = Array.isArray(params) ? params : [];
              pushLog({ api: 'websql', method: 'SQL', url: rawSql.slice(0, 120), body_len: JSON.stringify(values).length });
              try {
                if (upperSql.includes('SELECT')) {
                  const key = String(values[0] || '');
                  const value = webSqlStore.has(key) ? webSqlStore.get(key) : undefined;
                  if (typeof successCallback === 'function') successCallback(tx, makeResult(value));
                  return;
                }
                if (upperSql.includes('INSERT') || upperSql.includes('REPLACE') || upperSql.includes('UPDATE')) {
                  const key = String(values[0] || '');
                  const value = String(values[1] || '');
                  if (key) webSqlStore.set(key, value);
                  if (typeof successCallback === 'function') successCallback(tx, makeResult(undefined));
                  return;
                }
                if (upperSql.includes('DELETE')) {
                  const key = String(values[0] || '');
                  if (key) webSqlStore.delete(key);
                  if (typeof successCallback === 'function') successCallback(tx, makeResult(undefined));
                  return;
                }
                if (typeof successCallback === 'function') successCallback(tx, makeResult(undefined));
              } catch (err) {
                if (typeof errorCallback === 'function') {
                  try { errorCallback(tx, err); } catch (_) {}
                }
              }
            },
          };
          try {
            cb(tx);
          } catch (_) {}
        },
      };
    },
    requestFileSystem(_type, _size, successCallback){ if (typeof successCallback === 'function') successCallback({ root: {} }); },
    webkitRequestFileSystem(_type, _size, successCallback){ if (typeof successCallback === 'function') successCallback({ root: {} }); },
    fetch: async (url, options = {}) => {
      const reqUrl = String(url || '');
      const reqMethod = String(options.method || 'GET').toUpperCase();
      const bodyText = String(options.body || '');
      const reqHeaders = options.headers && typeof options.headers === 'object' ? options.headers : {};
      pushLog({ api: 'fetch', method: reqMethod, url: reqUrl, body_len: bodyText.length });
      if (reqUrl.toLowerCase().includes('riskct.geetest.com') && reqUrl.toLowerCase().includes('client_report')) {
        triggerCapture('fetch', reqUrl, reqHeaders, bodyText);
      }
      const payload = { status: 'success', code: 0, data: { gee_token: 'RzA_mock' } };
      return { ok: true, status: 200, text: async () => JSON.stringify(payload), json: async () => payload };
    },
    matchMedia: () => ({ matches: false, media: '', onchange: null, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}, dispatchEvent(){ return false; } }),
    addEventListener(type, fn){
      const t = String(type || '').toLowerCase();
      if ((t === 'load' || t === 'domcontentloaded') && typeof fn === 'function') {
        setTimeout(() => { try { fn(); } catch (_) {} }, 0);
        return;
      }
      windowEvents.add(t, fn);
    },
    removeEventListener(type, fn){
      windowEvents.remove(type, fn);
    },
    dispatchEvent(event){
      const t = String((event && event.type) || '').toLowerCase();
      windowEvents.dispatch(t, event);
      return true;
    },
    postMessage(data, origin){
      windowEvents.dispatch('message', {
        type: 'message',
        data,
        origin: String(origin || parsedTarget.origin || ''),
        source: ctx,
      });
    },
    __geetokenPatch(h, o, f){
      applyGeeProfilePatch(h, o, f);
    },
  };
  ctx.window = ctx;
  ctx.self = ctx;
  ctx.global = ctx;
  ctx.globalThis = ctx;
  ctx.top = ctx;
  ctx.parent = ctx;
  if (!ctx.crypto || typeof ctx.crypto !== 'object') ctx.crypto = {};
  if (typeof ctx.crypto.getRandomValues !== 'function') {
    ctx.crypto.getRandomValues = (arr) => {
      if (!arr || typeof arr.length !== 'number') return arr;
      const buf = nodeCrypto.randomBytes(arr.length);
      for (let i = 0; i < arr.length; i++) arr[i] = buf[i];
      return arr;
    };
  }
  if (typeof ctx.crypto.randomUUID !== 'function') {
    ctx.crypto.randomUUID = () => nodeCrypto.randomUUID();
  }

  vm.createContext(ctx);

  const waitWithTimeout = async (factory, timeoutMs) => {
    let localTimedOut = false;
    const result = await Promise.race([
      factory(),
      new Promise((resolve) => setTimeout(() => {
        localTimedOut = true;
        resolve({ __timeout: true });
      }, timeoutMs)),
    ]);
    return { result, timedOut: localTimedOut };
  };

  const preData = prePayload && typeof prePayload.data === 'object' ? prePayload.data : {};
  const preGToken = String((preData && preData.g_token) || '');
  if (!preGToken) {
    emitResult({ ok: false, error: 'pre_load g_token missing' });
    return;
  }

  let err = '';
  let loadData = null;
  let timedOut = false;
  let loadMode = '';

  try {
    vm.runInContext(gtJs, ctx);
    const initGeeGuard = ctx.initGeeGuard || (ctx.window && ctx.window.initGeeGuard);
    if (typeof initGeeGuard === 'function') {
      loadMode = 'initGeeGuard';
      const wrapped = await waitWithTimeout(
        () =>
          new Promise((resolve, reject) => {
            let settled = false;
            const done = (value) => {
              if (settled) return;
              settled = true;
              resolve(value);
            };
            try {
              initGeeGuard(
                {
                  appId,
                  https: true,
                  protocol: 'https://',
                },
                done,
              );
            } catch (innerErr) {
              if (settled) return;
              settled = true;
              reject(innerErr);
            }
          }),
        18000,
      );
      loadData = wrapped.result;
      timedOut = wrapped.timedOut;
    }
  } catch (e) {
    err = String(e && e.stack ? e.stack : e);
  }

  if ((!capture.clientReportBody || !capture.clientReportBody.trim()) && !timedOut) {
    try {
      vm.runInContext(geeguardJs, ctx);
      const geeGuard = ctx.GeeGuard || (ctx.window && ctx.window.GeeGuard) || null;
      if (!geeGuard || typeof geeGuard.load !== 'function') {
        emitResult({
          ok: false,
          error: err || 'GeeGuard.load not available',
          stage: 'missing_geeguard_load',
          load_mode: loadMode || 'direct_geeguard',
          logs_tail: logs.slice(-12),
        });
        return;
      }

      loadMode = loadMode || 'direct_geeguard';
      const wrapped = await waitWithTimeout(
        () =>
          geeGuard.load({
            type: 'gt',
            appId,
            gToken: preGToken,
            offline: false,
          }),
        18000,
      );
      loadData = wrapped.result;
      timedOut = wrapped.timedOut;
      if (loadData && loadData.__timeout) {
        timedOut = true;
      }
    } catch (e) {
      if (!err) {
        err = String(e && e.stack ? e.stack : e);
      }
    }
  }

  const loadStatus = loadData && typeof loadData === 'object' ? String(loadData.status || '') : '';
  const loadPayload = loadData && typeof loadData.data === 'object' ? loadData.data : {};
  const gee = String((loadPayload && loadPayload.gee_token) || '');
  const sentBody = normalizeBody(capture.clientReportBody || '');
  const candidateBodies = [];
  for (let i = 0; i < bodyCandidates.length; i++) {
    const candidate = normalizeBody(bodyCandidates[i]);
    if (!candidate || !candidate.startsWith('R0VFAA')) continue;
    candidateBodies.push(candidate);
  }
  let finalBody = sentBody || gee;
  let strongestCandidate = '';
  for (let i = 0; i < candidateBodies.length; i++) {
    const candidate = candidateBodies[i];
    if (!strongestCandidate || candidate.length >= strongestCandidate.length) {
      strongestCandidate = candidate;
    }
  }
  if (strongestCandidate && strongestCandidate.length > finalBody.length) {
    finalBody = strongestCandidate;
  }
  emitResult({
    ok: !!sentBody && !timedOut,
    error: err,
    body: finalBody,
    sent_body: sentBody,
    sent_url: capture.clientReportUrl,
    sent_headers: capture.clientReportHeaders,
    load_mode: loadMode,
    load_status: loadStatus,
    load_msg: String((loadPayload && loadPayload.msg) || ''),
    timed_out: timedOut,
    gee_len: gee.length,
    candidate_lengths: candidateBodies.map((item) => item.length),
    logs_tail: logs.slice(-8),
    debug_h: ctx.__gee_last_h && typeof ctx.__gee_last_h === 'object' ? ctx.__gee_last_h : {},
    debug_env: ctx.__gee_last_env && typeof ctx.__gee_last_env === 'object' ? ctx.__gee_last_env : {},
    debug_du: ctx.__gee_last_du && typeof ctx.__gee_last_du === 'object' ? ctx.__gee_last_du : {},
    debug_uid: String(ctx.__gee_last_uid || ''),
    debug_local_id: String(ctx.__gee_last_local_id || ''),
    debug_et: Number(ctx.__gee_last_et || 0),
    debug_raw: String(ctx.__gee_last_raw || ''),
    debug_decode_483: (typeof ctx.VTzcy !== 'undefined' && ctx.VTzcy && typeof ctx.VTzcy.$_CO === 'function') ? String(ctx.VTzcy.$_CO(483) || '') : '',
  });
}

async function runJob(input) {
  try {
    await main(input);
  } catch (e) {
    const line = JSON.stringify({ ok: false, error: String(e && e.stack ? e.stack : e) }) + '\n';
    process.stdout.write(line);
  }
}

if (process.env.GEETOKEN_NODE_PERSISTENT === '1') {
  const readline = require('readline');
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  let chain = Promise.resolve();
  rl.on('line', (line) => {
    const raw = String(line || '').trim();
    if (!raw) return;
    chain = chain.then(async () => {
      let input = {};
      try {
        input = JSON.parse(raw);
      } catch (e) {
        process.stdout.write(JSON.stringify({ ok: false, error: `invalid json: ${String(e && e.message ? e.message : e)}` }) + '\n');
        return;
      }
      await runJob(input);
    });
  });
} else {
main().catch((e) => {
  const line = JSON.stringify({ ok: false, error: String(e && e.stack ? e.stack : e) }) + '\n';
  try {
    process.stdout.write(line, () => process.exit(0));
  } catch (_) {
    process.stdout.write(line);
    process.exit(0);
  }
});
}
"""


def _normalize_body(raw: Any) -> str:
    text = str(raw or "").strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text


def _wrap_payload(body: str) -> str:
    # O body do client_report no browser e o base64 PURO (sem aspas).
    # A funcao anterior envolvia em aspas e o servidor recebia um body
    # invalido (JSON de um string, nao o base64 bruto).
    return str(body or "").strip()


def _parse_jsonp_payload(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    match = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", raw, flags=re.S)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_last_json(stdout: str) -> Dict[str, Any]:
    for raw_line in reversed(str(stdout or "").splitlines()):
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _node_generator_input(runtime_inputs: Dict[str, Any], user_agent: str, proxy_url: str = "") -> Dict[str, Any]:
    return {
        "gt_js": str(runtime_inputs.get("gt_js") or ""),
        "geeguard_js": _instrument_geeguard_js(str(runtime_inputs.get("geeguard_js") or "")),
        "pre_payload": runtime_inputs.get("pre_payload") if isinstance(runtime_inputs.get("pre_payload"), dict) else {},
        "appid": str(runtime_inputs.get("appid") or DEFAULT_GEETEST_APPID),
        "target_page_url": str(runtime_inputs.get("target_page_url") or ""),
        "user_agent": str(user_agent or ""),
        "language": str(runtime_inputs.get("language") or "pt-BR"),
        "profile_patch": runtime_inputs.get("profile_patch") if isinstance(runtime_inputs.get("profile_patch"), dict) else {},
        "proxy_url": proxy_url,
    }


class _PersistentNodeRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen[str]] = None
        self._script_path = ""
        self._stdout_queue: queue.Queue[str] = queue.Queue()
        self._stderr_tail: list[str] = []

    def request(self, node_input: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
        with self._lock:
            self._ensure_started()
            assert self._proc is not None and self._proc.stdin is not None
            try:
                self._proc.stdin.write(json.dumps(node_input, ensure_ascii=True) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.close()
                self._ensure_started()
                assert self._proc is not None and self._proc.stdin is not None
                try:
                    self._proc.stdin.write(json.dumps(node_input, ensure_ascii=True) + "\n")
                    self._proc.stdin.flush()
                except (BrokenPipeError, OSError) as retry_exc:
                    raise RuntimeError(f"direct_runtime: node persistente indisponivel: {retry_exc}") from exc

            try:
                line = self._stdout_queue.get(timeout=max(10, int(timeout_seconds)))
            except queue.Empty as exc:
                self.close()
                raise RuntimeError(f"direct_runtime: timeout no runner JS persistente ({timeout_seconds}s)") from exc
            payload = _parse_last_json(line)
            if not payload:
                raise RuntimeError(f"direct_runtime: resposta invalida do node persistente: {line[:200]!r}")
            return payload

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._script_path:
            try:
                os.unlink(self._script_path)
            except OSError:
                pass
            self._script_path = ""
        self._stdout_queue = queue.Queue()

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self.close()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as script_file:
            script_file.write(_NODE_RUNNER_SCRIPT)
            self._script_path = script_file.name
        env = os.environ.copy()
        env["GEETOKEN_NODE_PERSISTENT"] = "1"
        try:
            self._proc = subprocess.Popen(
                [_node_executable(), self._script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                **_hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as exc:
            self.close()
            raise RuntimeError(f"direct_runtime: node nao encontrado: {exc}")
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        proc = self._proc
        output_queue = self._stdout_queue
        if proc is None or proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            if line:
                output_queue.put(line)

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in iter(proc.stderr.readline, ""):
            line = str(line or "").strip()
            if line:
                self._stderr_tail.append(line)
                del self._stderr_tail[:-20]


class _NodeRunnerPool:
    """Pool de runners node persistentes.

    O runner singleton antigo segurava um threading.Lock durante TODA a
    requisicao (write no stdin + espera da resposta), serializando as
    geracoes de client_report/gee_token de contas paralelas: com N contas,
    a N-esima esperava (N-1) x 2-5s no node VM. O pool empresta um runner
    livre por requisicao e devolve ao final, mantendo o paralelismo das
    contas. Size via env GEETOKEN_NODE_POOL (0 = auto).
    """

    def __init__(self, size: int = 0) -> None:
        if size <= 0:
            try:
                size = int(os.getenv("GEETOKEN_NODE_POOL", "0") or "0")
            except Exception:
                size = 0
            if size <= 0:
                size = max(2, min(8, os.cpu_count() or 4))
        self._size = max(1, int(size))
        self.runners: list[_PersistentNodeRunner] = []
        self._free: queue.Queue[_PersistentNodeRunner] = queue.Queue()
        self._create_lock = threading.Lock()

    def _acquire(self) -> _PersistentNodeRunner:
        try:
            return self._free.get_nowait()
        except queue.Empty:
            pass
        with self._create_lock:
            if len(self.runners) < self._size:
                runner = _PersistentNodeRunner()
                self.runners.append(runner)
                return runner
        return self._free.get()

    def request(self, node_input: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
        runner = self._acquire()
        try:
            return runner.request(node_input, timeout_seconds)
        finally:
            self._free.put(runner)

    def close(self) -> None:
        for runner in self.runners:
            try:
                runner.close()
            except Exception:
                pass
        self.runners.clear()


    def ensure_size(self, size: int) -> None:
        """Garante pelo menos `size` runners no pool (chamado quando o bot
        conhece o paralelismo configurado, ex: parallel_count)."""
        try:
            target = max(1, int(size))
        except Exception:
            return
        with self._create_lock:
            while len(self.runners) < target:
                runner = _PersistentNodeRunner()
                self.runners.append(runner)
                self._free.put(runner)


_persistent_node_runner = _NodeRunnerPool()
atexit.register(_persistent_node_runner.close)


def _split_target_page(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return _configured_default_platform_url()
    if "://" not in raw:
        raw = "https://" + raw
    return raw


def _target_host(url: str) -> str:
    parsed = urlparse(_split_target_page(url))
    return str(parsed.netloc or "").strip().lower()


def _use_default_ss_desktop_profile(url: str) -> bool:
    host = _target_host(url)
    return host.endswith("377bet11.com")


def _resolve_runtime_user_agent(target_page_url: str, user_agent: str) -> str:
    if _use_default_ss_desktop_profile(target_page_url):
        return DEFAULT_SS_DESKTOP_UA
    text = str(user_agent or "").strip()
    return text or DEFAULT_SS_DESKTOP_UA


def _resolve_runtime_profile_patch(target_page_url: str) -> Dict[str, Any]:
    if not _use_default_ss_desktop_profile(target_page_url):
        return {}
    parsed = urlparse(_split_target_page(target_page_url))
    default_path = parsed.path or "/"
    if not default_path.endswith("/home/mine"):
        default_path = "/home/mine"
    env = json.loads(json.dumps(_REAL_DEFAULT_ENV_TEMPLATE))
    env["r13"] = f"{parsed.netloc}{default_path}" if parsed.netloc else ""
    return {
        "env": env,
        "du": json.loads(json.dumps(_REAL_DEFAULT_DU_TEMPLATE)),
        "tu": json.loads(json.dumps(_REAL_DEFAULT_TU_TEMPLATE)),
        "delete_uid": True,
        "force_ct": "3",
        "force_sign_empty": True,
    }


def _infer_language(page_html: str, fallback: str = "pt-BR") -> str:
    html = str(page_html or "")
    match = re.search(r"""<html[^>]+lang=["']([^"']+)["']""", html, flags=re.I)
    if match:
        value = str(match.group(1) or "").strip()
        if value:
            return value
    return fallback


def _infer_preload_client_type(target_page_url: str, user_agent: str) -> str:
    if _use_default_ss_desktop_profile(target_page_url):
        return "web"
    ua = str(user_agent or "").lower()
    if any(token in ua for token in ("android", "iphone", "ipad", "mobile")):
        return "h5"
    return "web"


def _instrument_geeguard_js(source: str) -> str:
    js = str(source or "")
    if not js:
        return js
    if "__gee_last_h" in js:
        return js
    needle = (
        r'"\u0067\u0065\u0065\u005f\u0074\u006f\u006b\u0065\u006e":gr(h),'
        r'"\u006c\u006f\u0063\u0061\u006c\u005f\u0069\u0064":u,'
    )
    replacement = (
        r'"\u0067\u0065\u0065\u005f\u0074\u006f\u006b\u0065\u006e":('
        r'typeof window.__geetokenPatch==="function"&&window.__geetokenPatch(h,o,f,a,d,u),'
        r'window.__gee_last_h=h,'
        r'window.__gee_last_env=o,'
        r'window.__gee_last_du=f,'
        r'window.__gee_last_uid=d,'
        r'window.__gee_last_local_id=u,'
        r'window.__gee_last_et=a,'
        r'window.__gee_last_raw=gr(h),'
        r'window.__gee_last_raw'
        r'),"\u006c\u006f\u0063\u0061\u006c\u005f\u0069\u0064":u,'
    )
    if needle in js:
        return js.replace(needle, replacement, 1)
    return js


def _extract_site_appid(page_html: str, fallback: str = DEFAULT_GEETEST_APPID) -> str:
    html = str(page_html or "")
    patterns = (
        r'geetestDeviceAppId:"([^"]+)"',
        r"geetestDeviceAppId:'([^']+)'",
        r'geetestDeviceAndroidAppId:"([^"]+)"',
        r"geetestDeviceAndroidAppId:'([^']+)'",
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I)
        if match:
            value = str(match.group(1) or "").strip()
            if value:
                return value
    return str(fallback or DEFAULT_GEETEST_APPID)


async def fetch_runtime_inputs(
    target_page_url: str,
    *,
    user_agent: str,
    language: str = "pt-BR",
    appid: str = DEFAULT_GEETEST_APPID,
    timeout_seconds: int = 20,
    proxy_url: str = "",
) -> Dict[str, Any]:
    target_url = _split_target_page(target_page_url)
    resolved_user_agent = _resolve_runtime_user_agent(target_url, user_agent)
    preload_client_type = _infer_preload_client_type(target_url, resolved_user_agent)
    request_headers = {
        "user-agent": str(resolved_user_agent or "").strip(),
        "accept-language": str(language or "pt-BR"),
    }
    client_kwargs = {"timeout": timeout_seconds, "verify": False, "follow_redirects": True}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    async with httpx.AsyncClient(**client_kwargs) as client:
        page_resp = await client.get(target_url, headers=request_headers)
        page_html = str(page_resp.text or "")
        final_target_url = str(page_resp.url or target_url)
        final_language = _infer_language(page_html, fallback=language)
        resolved_appid = _extract_site_appid(page_html, fallback=appid)
        parsed = urlparse(final_target_url)
        target_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else _configured_default_platform_url().rstrip("/")
        gt_url = urljoin(target_origin, "/libs/rc/gt@5/gt.js")

        callback = f"geetest_{int(time.time() * 1000)}"
        pre_load_url = (
            "https://riskct.geetest.com/g2/api/v1/pre_load"
            f"?client_type={preload_client_type}&appid={resolved_appid}&callback={callback}"
        )
        pre_resp = await client.get(pre_load_url, headers=request_headers)
        if int(getattr(pre_resp, "status_code", 0) or 0) == 567:
            raise GeetestRateLimitError(
                "pre_load 567: IP sob rate-limit do GeeTest "
                "(use proxy ou aguarde cooldown do IP)"
            )
        pre_payload = _parse_jsonp_payload(pre_resp.text)
        data = pre_payload.get("data") if isinstance(pre_payload.get("data"), dict) else {}
        g_token = str(data.get("g_token") or "").strip()
        if not g_token:
            raise RuntimeError(
                f"direct_runtime: g_token vazio no pre_load (HTTP {int(getattr(pre_resp, 'status_code', 0) or 0)})"
            )

        js_path = str(data.get("js") or "").strip()
        static_path = str(data.get("static_path") or "").strip()
        geeguard_url = ""
        if js_path and static_path:
            geeguard_url = f"https://static.geetest.com{static_path}{js_path}"
        elif js_path:
            geeguard_url = f"https://static.geetest.com{js_path}"
        if not geeguard_url:
            raise RuntimeError("direct_runtime: geeguard_url ausente no pre_load")

        geeguard_resp = await client.get(geeguard_url, headers=request_headers)
        geeguard_js = str(geeguard_resp.text or "")
        if not geeguard_js:
            raise RuntimeError("direct_runtime: geeGuard.js vazio")

        # gt.js nem sempre e servido pela origem da plataforma (bet969 404).
        # Quando ausente, o VM cai no fallback geeGuard sem custo — nao ha
        # motivo para elevar erro, mas tambem nao se deve repassar um corpo
        # "Not Found" ao VM (gera SyntaxError interno antes do fallback).
        try:
            gt_resp = await client.get(gt_url, headers=request_headers)
            gt_js = str(gt_resp.text or "") if int(getattr(gt_resp, "status_code", 200) or 200) == 200 else ""
        except Exception:
            gt_js = ""

    return {
        "target_page_url": final_target_url,
        "resolved_user_agent": str(resolved_user_agent or ""),
        "language": final_language,
        "preload_client_type": preload_client_type,
        "profile_patch": _resolve_runtime_profile_patch(final_target_url or target_url),
        "pre_load_url": pre_load_url,
        "pre_payload": pre_payload,
        "gt_url": gt_url,
        "gt_js": gt_js,
        "geeguard_url": geeguard_url,
        "geeguard_js": geeguard_js,
        "g_token": g_token,
        "appid": str(resolved_appid or DEFAULT_GEETEST_APPID),
        "page_status": int(getattr(page_resp, "status_code", 0) or 0),
    }


def _run_node_generator(
    runtime_inputs: Dict[str, Any],
    *,
    user_agent: str,
    timeout_seconds: int,
    proxy_url: str = "",
) -> Dict[str, Any]:
    payload = _persistent_node_runner.request(
        _node_generator_input(runtime_inputs, user_agent, proxy_url),
        timeout_seconds=max(10, int(timeout_seconds)),
    )
    if not payload:
        raise RuntimeError("direct_runtime: stdout do node sem json valido")

    body = _normalize_body(payload.get("body") or payload.get("sent_body") or "")
    if not body:
        raise RuntimeError(f"direct_runtime: body vazio error={payload.get('error')!r}")
    if not body.startswith("R0VFAA"):
        raise RuntimeError(f"direct_runtime: body inesperado prefix={body[:24]!r}")

    return {
        "payload": _wrap_payload(body),
        "payload_body": body,
        "payload_len": len(_wrap_payload(body)),
        "payload_body_len": len(body),
        "runner_error": str(payload.get("error") or ""),
        "runner_sent_url": str(payload.get("sent_url") or ""),
        "runner_sent_headers": payload.get("sent_headers") if isinstance(payload.get("sent_headers"), dict) else {},
        "load_status": str(payload.get("load_status") or ""),
        "load_msg": str(payload.get("load_msg") or ""),
        "runner_timed_out": bool(payload.get("timed_out")),
        "gee_len": int(payload.get("gee_len") or 0),
        "logs_tail": payload.get("logs_tail") if isinstance(payload.get("logs_tail"), list) else [],
        "debug_h": payload.get("debug_h") if isinstance(payload.get("debug_h"), dict) else {},
        "debug_env": payload.get("debug_env") if isinstance(payload.get("debug_env"), dict) else {},
        "debug_du": payload.get("debug_du") if isinstance(payload.get("debug_du"), dict) else {},
        "debug_uid": str(payload.get("debug_uid") or ""),
        "debug_local_id": str(payload.get("debug_local_id") or ""),
        "debug_et": int(payload.get("debug_et") or 0),
        "debug_raw_len": len(str(payload.get("debug_raw") or "")),
        "debug_decode_483": str(payload.get("debug_decode_483") or ""),
    }


async def build_client_report_payload(
    target_page_url: str,
    *,
    user_agent: str,
    language: str = "pt-BR",
    appid: str = DEFAULT_GEETEST_APPID,
    timeout_seconds: int = 25,
    proxy_url: str = "",
) -> Dict[str, Any]:
    # Rate-limit do GeeTest (HTTP 567 no pre_load) e por IP; retry com backoff
    # cobre bloqueios leves. Bloqueios longos so saem com proxy ou cooldown.
    retry_attempts = max(0, int(os.getenv("GEETEST_PRELOAD_RETRIES", "2") or "2"))
    try:
        backoff_s = max(0.0, float(os.getenv("GEETEST_PRELOAD_RETRY_BACKOFF_S", "3") or "3"))
    except ValueError:
        backoff_s = 3.0
    last_error: Optional[GeetestRateLimitError] = None
    runtime_inputs: Dict[str, Any] = {}
    for attempt in range(retry_attempts + 1):
        try:
            runtime_inputs = await fetch_runtime_inputs(
                target_page_url,
                user_agent=user_agent,
                language=language,
                appid=appid,
                timeout_seconds=max(8, int(timeout_seconds)),
                proxy_url=proxy_url,
            )
            last_error = None
            break
        except GeetestRateLimitError as exc:
            last_error = exc
            if attempt >= retry_attempts:
                break
            await asyncio.sleep(backoff_s * (attempt + 1))
    if last_error is not None:
        raise last_error
    resolved_user_agent = str(runtime_inputs.get("resolved_user_agent") or user_agent or "")
    generated = await asyncio.to_thread(
        _run_node_generator,
        runtime_inputs,
        user_agent=resolved_user_agent,
        timeout_seconds=max(10, int(timeout_seconds)),
        proxy_url=proxy_url,
    )
    return {
        **generated,
        "source": "direct_runtime",
        "resolved_user_agent": resolved_user_agent,
        "pre_load_url": str(runtime_inputs.get("pre_load_url") or ""),
        "gt_url": str(runtime_inputs.get("gt_url") or ""),
        "geeguard_url": str(runtime_inputs.get("geeguard_url") or ""),
        "g_token_len": len(str(runtime_inputs.get("g_token") or "")),
        "preload_client_type": str(runtime_inputs.get("preload_client_type") or ""),
        "target_page_url": str(runtime_inputs.get("target_page_url") or ""),
        "language": str(runtime_inputs.get("language") or language or "pt-BR"),
        "page_status": int(runtime_inputs.get("page_status") or 0),
    }


def _debug_log(message: str) -> None:
    if runtime_config.get("DEBUG_MODE"):
        logger.info(message)


def _sqlite_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _normalize_url(url_or_host: str) -> str:
    raw = str(url_or_host or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    return raw


def _normalize_plataforma(url_or_host: str) -> str:
    return _target_host(_normalize_url(url_or_host))


def _is_real_token(token: str) -> bool:
    value = str(token or "").strip()
    return bool(value and value != GEETOKEN_FAILURE_GATE and value != "disabled")


def _is_healthy_geetoken(token: str) -> bool:
    value = str(token or "").strip()
    return _is_real_token(value)


def _has_failure_gate(plataforma: str) -> bool:
    with get_geetokens_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM tokens WHERE plataforma = ? AND token = ? LIMIT 1",
            (plataforma, GEETOKEN_FAILURE_GATE),
        ).fetchone()
        return row is not None


def _insert_failure_gate(plataforma: str) -> None:
    if not plataforma:
        return
    with get_geetokens_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO tokens (plataforma, token, tamanho, limite, usos, data)
            VALUES (?, ?, ?, 0, 0, ?)
            """,
            (plataforma, GEETOKEN_FAILURE_GATE, len(GEETOKEN_FAILURE_GATE), _sqlite_now()),
        )
        conn.commit()


def _insert_geetoken(plataforma: str, token: str, limite: int, usos: int = 0) -> None:
    if not plataforma or not _is_healthy_geetoken(token):
        return
    with get_geetokens_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO tokens (plataforma, token, tamanho, limite, usos, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (plataforma, token, len(token), max(1, int(limite)), max(0, int(usos)), _sqlite_now()),
        )
        conn.commit()


def _reserve_by_query(where_sql: str, params: tuple) -> Optional[str]:
    with get_geetokens_db() as conn:
        row = conn.execute(
            f"""
            UPDATE tokens
            SET usos = usos + 1
            WHERE id = (
                SELECT id
                FROM tokens
                WHERE {where_sql}
                ORDER BY usos ASC, data ASC, id ASC
                LIMIT 1
            )
            RETURNING token
            """,
            params,
        ).fetchone()
        conn.commit()
        return str(row["token"]) if row else None


def _reserve_geetoken(plataforma: str) -> Optional[str]:
    token = _reserve_by_query(
        "plataforma = ? AND token != ? AND limite > 0 AND usos < limite",
        (plataforma, GEETOKEN_FAILURE_GATE),
    )
    if token:
        return token
    return _reserve_by_query(
        "token != ? AND limite > 0 AND usos < limite",
        (GEETOKEN_FAILURE_GATE,),
    )


def _available_count(plataforma: Optional[str] = None) -> int:
    with get_geetokens_db() as conn:
        if plataforma:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM tokens
                WHERE plataforma = ? AND token != ? AND limite > 0 AND usos < limite
                """,
                (plataforma, GEETOKEN_FAILURE_GATE),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM tokens
                WHERE token != ? AND limite > 0 AND usos < limite
                """,
                (GEETOKEN_FAILURE_GATE,),
            ).fetchone()
        return int(row["total"] or 0)


def _latest_success_platform() -> Optional[str]:
    with get_geetokens_db() as conn:
        row = conn.execute(
            """
            SELECT plataforma
            FROM tokens
            WHERE token != ? AND limite > 0
            ORDER BY data DESC, id DESC
            LIMIT 1
            """,
            (GEETOKEN_FAILURE_GATE,),
        ).fetchone()
        return str(row["plataforma"]) if row else None


def _platform_url_from_netloc(plataforma: str) -> str:
    host = str(plataforma or "").strip()
    if not host:
        return ""
    return host if "://" in host else f"https://{host}"


def _cleanup_expired_geetokens(ttl_seconds: int) -> int:
    cutoff = (datetime.now(UTC) - timedelta(seconds=max(1, int(ttl_seconds)))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with get_geetokens_db() as conn:
        cursor = conn.execute(
            "DELETE FROM tokens WHERE token != ? AND limite > 0 AND data < ?",
            (GEETOKEN_FAILURE_GATE, cutoff),
        )
        deleted = cursor.rowcount
        conn.commit()
        return int(deleted or 0)


def _build_direct_headers(target_url: str, user_agent: str) -> Dict[str, str]:
    parsed = urlparse(_normalize_url(target_url))
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    now_ts = str(int(time.time()))
    headers = {
        "client-type": "3",
        "appid": DEFAULT_GEETEST_APPID,
        "api-version": "1",
        "content-type": "application/x-www-form-urlencoded",
        "accept": "*/*",
        "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "timestamp": now_ts,
        "x-request-id": str(uuid.uuid4()),
        "x-device-type": "APK",
        "appsystem": "Android 14",
        "browsertype": "Mobile Chrome",
        "devicebrand": "Android",
        "devicemodel": "Android",
        "operatingsystem": "Android",
        "physicaldevicemodel": "Android",
        "user-agent": user_agent,
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "x-device": "2-1",
    }
    if origin:
        headers["origin"] = origin
        headers["referer"] = f"{origin}/"
        headers["x-custom-referer"] = _normalize_url(target_url)
    if parsed.netloc:
        headers["domain"] = parsed.netloc
        headers["webauthndomain"] = parsed.netloc
    return headers


class GeetokenManager:
    def __init__(self, config: Optional[GeetokenConfig] = None, proxy_config: Optional[ProxyConfig] = None):
        self.config = config or GeetokenConfig()
        self.proxy_config = proxy_config
        self._locks: Dict[str, asyncio.Lock] = {}
        self._collector_task: Optional[asyncio.Task] = None
        self._collector_stop = asyncio.Event()
        self._run_active = False
        self._run_url = ""
        self._run_remaining = 0
        self._collector_url = ""
        init_geetokens_db()

    def _get_lock(self, plataforma: str) -> asyncio.Lock:
        if plataforma not in self._locks:
            self._locks[plataforma] = asyncio.Lock()
        return self._locks[plataforma]

    def configure_run(self, url: str, total_accounts: int) -> None:
        self._run_active = True
        self._run_url = _normalize_url(url)
        self._run_remaining = max(0, int(total_accounts or 0))

    def configure_collector_target(self, url: str) -> None:
        self._collector_url = _normalize_url(url)

    def update_run_remaining(self, remaining: int) -> None:
        self._run_remaining = max(0, int(remaining or 0))

    async def stop_run(self) -> None:
        self._run_active = False
        self._run_remaining = 0
        await self.stop_background_collector()

    def mark_token_used(self, url_or_host: str, token: str) -> None:
        if _is_real_token(token):
            _debug_log(f"[Geetoken] Token usado para {_normalize_plataforma(url_or_host)}")

    async def get_token(
        self,
        url_or_host: str,
        force_new: bool = False,
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        target_url = _normalize_url(url_or_host)
        plataforma = _normalize_plataforma(target_url)
        if not plataforma:
            return "disabled"
        if not force_new:
            cached = _reserve_geetoken(plataforma)
            if cached:
                return cached
        lock = self._get_lock(plataforma)
        async with lock:
            if not force_new:
                cached = _reserve_geetoken(plataforma)
                if cached:
                    return cached
            collected = await self._collect_with_platform_policy(target_url, custom_headers, user_agent)
            if not collected:
                return "disabled"
            token, token_platform = collected
            _insert_geetoken(token_platform, token, self.config.max_uses, usos=1 if not force_new else 0)
            return token

    async def _collect_with_platform_policy(
        self,
        target_url: str,
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[tuple[str, str]]:
        candidates = []
        default_url = _normalize_url(self.config.plataforma_padrao)
        default_platform = _normalize_plataforma(default_url)
        current_url = _normalize_url(target_url)
        current_platform = _normalize_plataforma(current_url)
        # Modo individual: coleta EXCLUSIVAMENTE da plataforma alvo. A política
        # de fallback (padrao hardcoded -> alvo -> ultima com sucesso) vale para
        # o estoque/cache; token individual tem que bater com a origem do
        # registro, senao validate/v4 responde 1130/405.
        if getattr(self.config, "individual", False):
            if current_platform:
                token = await self._fetch_token_via_api(current_url, custom_headers, user_agent)
                if token:
                    return token, current_platform
            return None
        if default_url and default_platform:
            candidates.append(default_url)
        if (
            self.config.coleta_por_plataforma_ativa
            and current_platform
            and current_platform != default_platform
        ):
            candidates.append(current_url)
        latest = _latest_success_platform()
        if latest and latest not in {current_platform, default_platform}:
            candidates.append(_platform_url_from_netloc(latest))
        if default_url and _normalize_plataforma(default_url) not in {_normalize_plataforma(item) for item in candidates}:
            candidates.append(default_url)

        for candidate in candidates:
            candidate_platform = _normalize_plataforma(candidate)
            if not candidate_platform:
                continue
            token = await self._fetch_token_via_api(candidate, custom_headers, user_agent)
            if token:
                return token, candidate_platform
        return None

    async def _post_client_report_httpcloak(
        self,
        payload: str,
        headers: Dict[str, str],
        target_url: str,
        timeout: int,
        proxy_url: str = "",
    ):
        """POST client_report via httpcloak (TLS de Chrome Android real).

        Portado do replay.py do projeto API: preset chrome-*-android +
        warmup na URL alvo (aquece cookies/H2 do mesmo "browser" que vai
        falar com o GeeTest). Retorna objeto Response-like ou None se
        httpcloak indisponivel/falhou (caller usa fallback curl_cffi).
        """
        try:
            import httpcloak  # noqa: PLC0415
        except Exception as exc:
            _debug_log(f"[Geetoken] httpcloak indisponivel: {exc}")
            return None

        def _run():
            preset = os.getenv("HTTPCLOAK_PRESET", "").strip()
            if not preset:
                profile = os.getenv("HTTP_PROFILE", "chrome131_android").strip()
                preset = {
                    "chrome150": "chrome-150",
                    "chrome145": "chrome-145",
                    "chrome131_android": "chrome-145-android",
                    "edge101": "chrome-101",
                    "firefox147": "firefox-147",
                    "firefox144": "firefox-144",
                    "safari2601": "safari-2601",
                    "safari180": "safari-180",
                }.get(profile, "chrome-145-android")
            kwargs = {
                "preset": preset,
                "timeout": max(10, int(timeout)),
                "http_version": "auto",
                "verify": True,
                "allow_redirects": True,
                "prefer_ipv4": True,
            }
            if proxy_url:
                kwargs["proxy"] = proxy_url
            session = httpcloak.Session(**kwargs)
            try:
                # warmup (priming) na plataforma alvo: mesma tecnica do
                # replay.py (PAGE_PRIMER_MODE=warmup_then_get)
                try:
                    session.warmup(target_url)
                except Exception:
                    try:
                        session.get(target_url, timeout=max(8, int(timeout)))
                    except Exception:
                        pass
                return session.post(
                    "https://riskct.geetest.com/g2/api/v1/client_report",
                    data=payload,
                    headers=headers,
                )
            finally:
                try:
                    session.close()
                except Exception:
                    pass

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            _debug_log(f"[Geetoken] httpcloak client_report falhou: {exc}")
            return None

    async def _fetch_token_via_api(
        self,
        target_url: str,
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[str]:
        impersonate_name, browser_user_agent = _select_browser_profile(BROWSER_PROFILES_ANDROID)
        final_user_agent = str(user_agent or browser_user_agent or "").strip()
        timeout = max(10, int(self.config.fetch_timeout_seconds or 30))
        proxy_url = ""
        if self.proxy_config is not None and self.proxy_config.usar_proxy:
            proxy_url = self.proxy_config.proxy_url(default_scheme="http")
        try:
            # pre_load/geeguard/client_report pelo MESMO canal do client_report.
            # Sem proxy, o pre_load sai pelo IP local; quando esse IP cai no
            # rate-limit do GeeTest (HTTP 567), o registro inteiro morre mesmo
            # com proxy ativo. Usando o mesmo proxy nos dois, nao ha mismatch
            # de IP entre pre_load e client_report.
            payload_info = await build_client_report_payload(
                target_url,
                user_agent=final_user_agent,
                language="pt-BR",
                timeout_seconds=timeout,
                proxy_url=proxy_url,
            )
            payload = str(payload_info.get("payload") or "").strip()
            if not payload:
                return None
            resolved_ua = str(payload_info.get("resolved_user_agent") or final_user_agent or "")
            headers = _build_direct_headers(target_url, resolved_ua)
            if custom_headers:
                headers.update(custom_headers)
                headers["appid"] = DEFAULT_GEETEST_APPID
                headers["content-type"] = "application/x-www-form-urlencoded"
            headers["user-agent"] = resolved_ua

            # Emissao via HTTPCLOAK quando disponivel: preset TLS de Chrome
            # Android REAL (JA3/JA4/HTTP2 de browser) + warmup na plataforma
            # alvo antes do client_report — replica o fluxo do replay.py do
            # projeto API que produzia geetokens aceitos pela campanha de
            # bonus. curl_cffi fica como fallback; httpx nunca toca o POST.
            proxy_url = ""
            if self.proxy_config is not None and self.proxy_config.usar_proxy:
                proxy_url = self.proxy_config.proxy_url(default_scheme="http")
            response = await self._post_client_report_httpcloak(
                payload, headers, target_url, timeout, proxy_url
            )
            if response is None:
                session_kwargs = {
                    "impersonate": impersonate_name,
                    "timeout": timeout,
                    "extra_fp": _get_extra_fp(impersonate_name),
                    "verify": False,
                    "allow_redirects": True,
                }
                if proxy_url:
                    session_kwargs["proxy"] = proxy_url
                async with AsyncSession(**session_kwargs) as client:
                    response = await client.post(
                        "https://riskct.geetest.com/g2/api/v1/client_report",
                        data=payload,
                        headers=headers,
                    )
            if int(getattr(response, "status_code", 0) or 0) != 200:
                return None
            try:
                data = response.json()
            except Exception:
                return None
            nested = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else {}
            token = str(nested.get("gee_token") or data.get("gee_token") or "").strip() if isinstance(data, dict) else ""
            return token if _is_healthy_geetoken(token) else None
        except GeetestRateLimitError as exc:
            _debug_log(
                f"[Geetoken] Rate-limit GeeTest (567) no pre_load para "
                f"{_normalize_plataforma(target_url)}: IP bloqueado pelo riskct.geetest.com. "
                f"Ative proxy (--proxy) ou aguarde o cooldown. Detalhe: {exc}"
            )
            return None
        except Exception as exc:
            _debug_log(f"[Geetoken] Coleta direta falhou para {_normalize_plataforma(target_url)}: {exc}")
            return None

    async def collect_for_stock_once(self) -> int:
        if getattr(self.config, "individual", False):
            # Individual mode has no shared stock.  Do not run the background
            # collector or consult plataforma_padrao (historically 377bet11).
            return 0
        _cleanup_expired_geetokens(self.config.valid_ttl_seconds)
        target_url = self._collector_target_url()
        plataforma = _normalize_plataforma(target_url)
        if not plataforma:
            return 0
        disponiveis = _available_count(plataforma)
        # Durante execução ativa, só tenta buscar fora quando o banco inteiro zerar.
        if self._run_active and _available_count() > 0:
            return 0
        faltam = max(0, int(self.config.estoque_por_plataforma) - disponiveis)
        if faltam <= 0:
            return 0
        total = min(max(1, int(self.config.tokens_por_coleta)), faltam)
        collected = 0
        for _ in range(total):
            item = await self._collect_with_platform_policy(target_url)
            if not item:
                break
            token, token_platform = item
            if _is_healthy_geetoken(token):
                _insert_geetoken(token_platform, token, self.config.max_uses, usos=0)
                collected += 1
        return collected

    def _collector_target_url(self) -> str:
        if self.config.coleta_por_plataforma_ativa and self._collector_url:
            plataforma = _normalize_plataforma(self._collector_url)
            if plataforma:
                return self._collector_url
        default_url = _normalize_url(self.config.plataforma_padrao)
        default_platform = _normalize_plataforma(default_url)
        if default_platform:
            return default_url
        if self._run_active and self.config.coleta_por_plataforma_ativa and self._run_url:
            plataforma = _normalize_plataforma(self._run_url)
            if plataforma:
                return self._run_url
        latest = _latest_success_platform()
        if latest:
            return _platform_url_from_netloc(latest)
        return _normalize_url(self.config.plataforma_padrao)

    def _collector_interval(self) -> int:
        if not self._run_active:
            return max(1, int(self.config.intervalo_sem_run_segundos))
        required = math.ceil(max(0, self._run_remaining) / max(1, int(self.config.max_uses)))
        available = _available_count()
        if available >= required:
            return max(1, int(self.config.intervalo_com_run_segundos))
        return max(1, int(self.config.intervalo_sem_run_segundos))

    def start_background_collector(self) -> None:
        if getattr(self.config, "individual", False):
            return
        if self._collector_task and not self._collector_task.done():
            return
        self._collector_stop = asyncio.Event()
        self._collector_task = asyncio.create_task(self._background_loop())

    async def stop_background_collector(self) -> None:
        if not self._collector_task:
            return
        self._collector_stop.set()
        try:
            await asyncio.wait_for(self._collector_task, timeout=5)
        except Exception:
            self._collector_task.cancel()
        self._collector_task = None

    async def _background_loop(self) -> None:
        while not self._collector_stop.is_set():
            try:
                await self.collect_for_stock_once()
            except Exception as exc:
                _debug_log(f"[Geetoken] Erro no coletor em segundo plano: {exc}")
            try:
                await asyncio.wait_for(self._collector_stop.wait(), timeout=self._collector_interval())
            except asyncio.TimeoutError:
                pass


_geetoken_manager: Optional[GeetokenManager] = None


def get_geetoken_manager(
    config: Optional[GeetokenConfig] = None,
    proxy_config: Optional[ProxyConfig] = None,
) -> GeetokenManager:
    global _geetoken_manager
    if _geetoken_manager is None:
        _geetoken_manager = GeetokenManager(config, proxy_config)
    elif config is not None:
        _geetoken_manager.config = config
        _geetoken_manager.proxy_config = proxy_config
    elif proxy_config is not None:
        _geetoken_manager.proxy_config = proxy_config
    return _geetoken_manager


async def get_geetoken(
    url_or_host: str,
    config: Optional[GeetokenConfig] = None,
    proxy_config: Optional[ProxyConfig] = None,
    force_new: bool = False,
) -> str:
    manager = get_geetoken_manager(config, proxy_config)
    return await manager.get_token(url_or_host, force_new=force_new)


def mark_geetoken_used(url_or_host: str, token: str) -> None:
    manager = get_geetoken_manager()
    manager.mark_token_used(url_or_host, token)


async def get_geetoken_individual(
    url_or_host: str,
    proxy_config: Optional[ProxyConfig] = None,
) -> str:
    manager = get_geetoken_manager(proxy_config=proxy_config)
    token = await manager._fetch_token_via_api(url_or_host)
    return token or "disabled"
