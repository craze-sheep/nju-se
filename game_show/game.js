"use strict";

(() => {
  const SIZE = 4;
  const WIN_TILE = 2048;
  const FOUR_PROB = 0.1;   // 新方块为 4 的概率，其余为 2
  const GAP = 12;          // 与 style.css 的 --gap 保持一致
  const MOVE_MS = 120;
  const POP_MS = 180;

  const boardEl = document.getElementById("board");
  const gridEl = document.getElementById("grid");
  const tileLayerEl = document.getElementById("tiles");
  const scoreEl = document.getElementById("score");
  const bestEl = document.getElementById("best");
  const overlayEl = document.getElementById("overlay");
  const overlayTextEl = document.getElementById("overlay-text");
  const btnNewEl = document.getElementById("btn-new");
  const btnAgainEl = document.getElementById("btn-again");

  let grid = [];
  let score = 0;
  let best = 0;
  let busy = false;
  let won = false;
  let overlayAction = null;
  let tileEls = {};   // "r,c" -> 元素
  let tileSeq = 0;
  let tileW = 0;

  // ---------- 核心逻辑（纯函数） ----------

  function makeGrid() {
    return Array.from({ length: SIZE }, () => Array(SIZE).fill(0));
  }

  function emptyCells(g) {
    const cells = [];
    for (let r = 0; r < SIZE; r++) {
      for (let c = 0; c < SIZE; c++) {
        if (g[r][c] === 0) cells.push({ r, c });
      }
    }
    return cells;
  }

  function addRandomTile(g) {
    const cells = emptyCells(g);
    if (cells.length === 0) return null;
    const pick = cells[Math.floor(Math.random() * cells.length)];
    const value = Math.random() < FOUR_PROB ? 4 : 2;
    g[pick.r][pick.c] = value;
    return { r: pick.r, c: pick.c, value };
  }

  function posAt(dir, line, offset) {
    switch (dir) {
      case "left":  return { r: line, c: offset };
      case "right": return { r: line, c: SIZE - 1 - offset };
      case "up":    return { r: offset, c: line };
      case "down":  return { r: SIZE - 1 - offset, c: line };
    }
  }

  // 执行一次移动：滑动 + 单次合并，返回 { grid, moves, gained, moved }
  // moves 覆盖每一个参与移动/合并的格子（含被合并的格子），
  // 便于渲染层同步清理旧元素，避免棋盘满后元素残留。
  function move(g, dir) {
    const result = makeGrid();
    const moves = [];
    let gained = 0;
    let moved = false;

    for (let line = 0; line < SIZE; line++) {
      const cells = [];
      for (let i = 0; i < SIZE; i++) {
        const p = posAt(dir, line, i);
        if (g[p.r][p.c] !== 0) cells.push({ r: p.r, c: p.c, value: g[p.r][p.c] });
      }
      let target = 0;
      for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        let value = cell.value;
        let merged = false;
        const to = posAt(dir, line, target);
        if (i + 1 < cells.length && cell.value === cells[i + 1].value) {
          value = cell.value * 2;
          merged = true;
          gained += value;
          const nextCell = cells[i + 1];
          // 被合并的格子：同样生成一条移动轨迹（落到同一目标，动画后会被移除）
          moves.push({ from: { r: nextCell.r, c: nextCell.c }, to, value: cell.value, merged: true });
          if (nextCell.r !== to.r || nextCell.c !== to.c) moved = true;
          i++;   // 每个值在同一轮内只合并一次
        }
        result[to.r][to.c] = value;
        if (cell.r !== to.r || cell.c !== to.c) moved = true;
        moves.push({ from: { r: cell.r, c: cell.c }, to, value, merged });
        target++;
      }
    }
    return { grid: result, moves, gained, moved };
  }

  function canMove(g) {
    for (let r = 0; r < SIZE; r++) {
      for (let c = 0; c < SIZE; c++) {
        if (g[r][c] === 0) return true;
        if (r + 1 < SIZE && g[r][c] === g[r + 1][c]) return true;
        if (c + 1 < SIZE && g[r][c] === g[r][c + 1]) return true;
      }
    }
    return false;
  }

  function maxTile(g) {
    return Math.max(...g.flat());
  }

  // ---------- 渲染 ----------

  function key(r, c) { return r + "," + c; }

  function tileClass(v) {
    if (v >= 4096) return "tile tile-super";
    return "tile tile-" + v;
  }

  function posXY(c, r) {
    return { x: c * (tileW + GAP), y: r * (tileW + GAP) };
  }

  function createTileEl(r, c, v) {
    const el = document.createElement("div");
    el.className = tileClass(v);
    el.textContent = v;
    el.dataset.r = r;
    el.dataset.c = c;
    el.dataset.id = tileSeq++;
    const p = posXY(c, r);
    el.style.width = tileW + "px";
    el.style.height = tileW + "px";
    el.style.transform = "translate(" + p.x + "px," + p.y + "px)";
    tileLayerEl.appendChild(el);
    return el;
  }

  function updateScore() {
    scoreEl.textContent = score;
    if (score > best) {
      best = score;
      try { localStorage.setItem("best2048", String(best)); } catch (e) { /* 忽略 */ }
    }
    bestEl.textContent = best;
  }

  function renderBoard() {
    tileLayerEl.innerHTML = "";
    tileEls = {};
    for (let r = 0; r < SIZE; r++) {
      for (let c = 0; c < SIZE; c++) {
        if (grid[r][c] !== 0) {
          const el = createTileEl(r, c, grid[r][c]);
          tileEls[key(r, c)] = el;
        }
      }
    }
    updateScore();
  }

  function layout() {
    tileW = (tileLayerEl.clientWidth - 3 * GAP) / 4;
    if (tileW <= 0) return;
    for (const el of tileLayerEl.children) {
      const r = +el.dataset.r;
      const c = +el.dataset.c;
      const p = posXY(c, r);
      el.style.width = tileW + "px";
      el.style.height = tileW + "px";
      el.style.transform = "translate(" + p.x + "px," + p.y + "px)";
    }
  }

  // ---------- 交互 ----------

  function hideOverlay() {
    overlayEl.classList.add("hidden");
    overlayAction = null;
  }

  function showOverlay(text, btnText, action) {
    overlayTextEl.textContent = text;
    btnAgainEl.textContent = btnText;
    overlayAction = action || null;
    overlayEl.classList.remove("hidden");
  }

  function startNewGame() {
    grid = makeGrid();
    score = 0;
    won = false;
    busy = false;
    hideOverlay();
    addRandomTile(grid);
    addRandomTile(grid);
    renderBoard();
  }

  function handleMove(dir) {
    if (busy) return;
    const res = move(grid, dir);
    if (!res.moved) return;
    grid = res.grid;
    score += res.gained;
    busy = true;

    // 1) 滑动：把现有方块移动到新位置，按目标位置分桶（合并对落在同一桶）
    const buckets = {};
    for (const mv of res.moves) {
      const fromK = key(mv.from.r, mv.from.c);
      const el = tileEls[fromK];
      if (!el) continue;
      const p = posXY(mv.to.c, mv.to.r);
      el.style.transform = "translate(" + p.x + "px," + p.y + "px)";
      el.dataset.r = mv.to.r;
      el.dataset.c = mv.to.c;
      const toK = key(mv.to.r, mv.to.c);
      (buckets[toK] = buckets[toK] || []).push({ el, merged: mv.merged, value: mv.value });
      delete tileEls[fromK];
    }

    // 2) 动画结束后：合并、随机生成新方块、胜负判定
    setTimeout(() => {
      for (const k in buckets) {
        const items = buckets[k];
        const keep = items[items.length - 1];
        if (items.length > 1 || keep.merged) {
          keep.el.className = tileClass(keep.value);
          keep.el.textContent = keep.value;
          keep.el.classList.add("pop");
          setTimeout(() => keep.el.classList.remove("pop"), POP_MS);
        }
        for (const item of items) {
          if (item !== keep) item.el.remove();
        }
        tileEls[k] = keep.el;
      }

      const nt = addRandomTile(grid);
      if (nt) {
        const el = createTileEl(nt.r, nt.c, nt.value);
        el.classList.add("pop");
        setTimeout(() => el.classList.remove("pop"), POP_MS);
        tileEls[key(nt.r, nt.c)] = el;
      }

      updateScore();

      if (!won && maxTile(grid) >= WIN_TILE) {
        won = true;
        showOverlay("你赢了！🎉 合成 2048", "继续挑战", hideOverlay);
      } else if (!canMove(grid)) {
        showOverlay("游戏结束", "再来一局", startNewGame);
      }
      busy = false;
    }, MOVE_MS);
  }

  // 键盘：方向键 + WASD
  document.addEventListener("keydown", (e) => {
    const map = {
      ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down",
      a: "left", d: "right", w: "up", s: "down",
      A: "left", D: "right", W: "up", S: "down"
    };
    const dir = map[e.key];
    if (dir) {
      e.preventDefault();
      handleMove(dir);
    }
  });

  // 触摸滑动（手机 / 平板）
  let touchStart = null;
  boardEl.addEventListener("touchstart", (e) => {
    touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }, { passive: true });
  boardEl.addEventListener("touchend", (e) => {
    if (!touchStart) return;
    const dx = e.changedTouches[0].clientX - touchStart.x;
    const dy = e.changedTouches[0].clientY - touchStart.y;
    touchStart = null;
    const ax = Math.abs(dx), ay = Math.abs(dy);
    if (Math.max(ax, ay) < 24) return;
    handleMove(ax > ay ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up"));
  }, { passive: true });

  btnNewEl.addEventListener("click", startNewGame);
  btnAgainEl.addEventListener("click", () => {
    if (overlayAction) overlayAction();
    else startNewGame();
  });

  window.addEventListener("resize", layout);

  // ---------- 初始化 ----------

  try { best = parseInt(localStorage.getItem("best2048") || "0", 10) || 0; } catch (e) { best = 0; }

  // 生成 16 个背景格
  for (let i = 0; i < SIZE * SIZE; i++) {
    const cell = document.createElement("div");
    cell.className = "grid-cell";
    gridEl.appendChild(cell);
  }

  startNewGame();
  layout();
})();
