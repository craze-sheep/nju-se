#!/usr/bin/env node
/**
 * 2048 网页版核心逻辑单元测试
 *
 * 从 game_show/2048.html 中提取内嵌 <script>（DOM 部分在无 document 时自动跳过），
 * 在 node 沙箱中执行并调用导出的核心函数进行断言。
 *
 * 运行：node game_show/tests/core.test.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const htmlPath = path.join(__dirname, "..", "2048.html");
const html = fs.readFileSync(htmlPath, "utf8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) {
  console.error("未在 2048.html 中找到 <script>");
  process.exit(1);
}

const sandbox = { module: { exports: {} }, exports: {} };
vm.createContext(sandbox);
vm.runInContext(m[1], sandbox);
const G = sandbox.module.exports;

let pass = 0;
let fail = 0;

function check(name, cond) {
  if (cond) {
    pass++;
    console.log("OK: " + name);
  } else {
    fail++;
    console.error("FAIL: " + name);
  }
}

function eq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// ---- 左移 ----
let g = G.makeGrid();
g[0] = [2, 2, 4, 0];
g[2] = [2, 0, 2, 4];
let r = G.move(g, "left");
check("left row0", eq(r.grid[0], [4, 4, 0, 0]));
check("left row2", eq(r.grid[2], [4, 4, 0, 0]));
check("left gain", r.gained === 8);
check("left moved", r.moved === true);
check("left moves count", r.moves.length === 4);

// ---- 右移 ----
g = G.makeGrid();
g[0] = [2, 2, 4, 0];
r = G.move(g, "right");
check("right row0", eq(r.grid[0], [0, 0, 4, 4]));
check("right gain", r.gained === 4);

// ---- 上移 ----
g = G.makeGrid();
g[0][0] = 2;
g[1][0] = 2;
g[1][1] = 4;
r = G.move(g, "up");
check("up board", eq(r.grid[0], [4, 4, 0, 0]) && r.grid[1][0] === 0);
check("up gain", r.gained === 4);

// ---- 下移 ----
g = G.makeGrid();
g[0][0] = 2;
g[1][0] = 2;
g[1][1] = 4;
r = G.move(g, "down");
check("down board", eq(r.grid[3], [4, 4, 0, 0]) && r.grid[0][0] === 0);
check("down gain", r.gained === 4);

// ---- 合并语义 ----
check("merge once 2222", eq(G.move([[2, 2, 2, 2], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], "left").grid[0], [4, 4, 0, 0]));
check("merge triple 2220", eq(G.move([[2, 2, 2, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], "left").grid[0], [4, 2, 0, 0]));
check("merge gap 2022", eq(G.move([[2, 0, 2, 2], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], "left").grid[0], [4, 2, 0, 0]));
check("no change 2424", G.move([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]], "left").moved === false);
check("adjacent merge 4480", eq(G.move([[4, 4, 8, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], "left").grid[0], [8, 8, 0, 0]));

// ---- 移动轨迹一致性 ----
g = [[2, 2, 4, 0], [0, 0, 0, 0], [2, 0, 2, 4], [0, 0, 0, 0]];
r = G.move(g, "left");
check("moves from valid", r.moves.every((mv) => g[mv.from.r][mv.from.c] !== 0));
check("moves to match grid", r.moves.every((mv) => r.grid[mv.to.r][mv.to.c] === mv.value));

// ---- canMove ----
check("canMove blocked", G.canMove([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]) === false);
check("canMove adjacent", G.canMove([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 4]]) === true);
check("canMove empty", G.canMove([[2, 4, 2, 4], [4, 2, 4, 2], [2, 0, 2, 4], [4, 2, 4, 2]]) === true);

// ---- addRandomTile / maxTile ----
g = G.makeGrid();
const nt = G.addRandomTile(g);
check("tile inserted", nt && g[nt.r][nt.c] !== 0 && (g[nt.r][nt.c] === 2 || g[nt.r][nt.c] === 4));
check("tile inserted once", G.emptyCells(g).length === 15);
g = G.makeGrid();
g[0][1] = 8;
check("maxTile", G.maxTile(g) === 8);

// ---- 随机对局模拟（1000 步） ----
let sim = G.makeGrid();
G.addRandomTile(sim);
G.addRandomTile(sim);
const dirs = ["left", "right", "up", "down"];
let stable = true;
for (let i = 0; i < 1000 && stable; i++) {
  const d = dirs[Math.floor(Math.random() * 4)];
  const rr = G.move(sim, d);
  if (rr.moved) {
    sim = rr.grid;
    G.addRandomTile(sim);
  }
  stable =
    sim.length === 4 &&
    sim.every((row) => row.length === 4 && row.every((v) => v >= 0 && Number.isInteger(v)));
}
check("sim 1000 steps stable", stable);

console.log("\n通过 " + pass + " 项, 失败 " + fail + " 项");
process.exit(fail ? 1 : 0);
