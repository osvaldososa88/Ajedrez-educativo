/**
 * Ajedrez Escolar - Puzzle Creator / Position Editor
 * Lets a student or teacher set up a position (place/move pieces, load FEN),
 * choose the side to move, and record a solution sequence, variations and hints
 * before saving the puzzle as a DRAFT. Legality of the recorded solution is
 * validated authoritatively by the server when the puzzle is submitted for review.
 */

const STARTING_GRID_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';

class PuzzleCreatorApp {
    constructor() {
        this.boardEl = document.getElementById('chessboard');
        if (!this.boardEl) return;

        this.grid = this.parsePlacement(STARTING_GRID_FEN);
        this.selectedTool = null; // active palette piece, or 'erase'
        this.selectedSquare = null; // for move-mode (no tool active)

        this.solutionMoves = [];
        this.variations = {}; // { "0": ["e2e4", ...] }
        this.hints = [];

        this.loadInitialData();
        this.buildPalette();
        this.renderBoard();
        this.syncFenDisplay();
        this.renderSolutionList();
        this.renderVariationList();
        this.renderHintList();
        this.initEvents();
    }

    loadInitialData() {
        if (typeof INITIAL_FEN !== 'undefined' && INITIAL_FEN) {
            this.grid = this.parsePlacement(INITIAL_FEN.split(' ')[0]);
            const turnChar = INITIAL_FEN.split(' ')[1];
            const sideSelect = document.getElementById('side_to_move');
            if (sideSelect && turnChar) {
                sideSelect.value = turnChar === 'b' ? 'BLACK' : 'WHITE';
            }
        }

        const solutionEl = document.getElementById('initial-solution-moves');
        if (solutionEl) this.solutionMoves = JSON.parse(solutionEl.textContent);

        const variationsEl = document.getElementById('initial-variations');
        if (variationsEl) this.variations = JSON.parse(variationsEl.textContent);

        const hintsEl = document.getElementById('initial-hints');
        if (hintsEl) this.hints = JSON.parse(hintsEl.textContent);
    }

    parsePlacement(placement) {
        const grid = [];
        const rows = placement.split('/');
        for (let r = 0; r < 8; r++) {
            const row = [];
            for (let c = 0; c < rows[r].length; c++) {
                const char = rows[r][c];
                if (!isNaN(char)) {
                    const emptyCount = parseInt(char);
                    for (let e = 0; e < emptyCount; e++) row.push(null);
                } else {
                    row.push(char);
                }
            }
            grid.push(row);
        }
        return grid;
    }

    gridToPlacement() {
        return this.grid.map(row => {
            let fenRow = '';
            let emptyCount = 0;
            row.forEach(cell => {
                if (cell === null) {
                    emptyCount += 1;
                } else {
                    if (emptyCount > 0) { fenRow += emptyCount; emptyCount = 0; }
                    fenRow += cell;
                }
            });
            if (emptyCount > 0) fenRow += emptyCount;
            return fenRow;
        }).join('/');
    }

    currentFen() {
        const sideSelect = document.getElementById('side_to_move');
        const turnChar = (sideSelect && sideSelect.value === 'BLACK') ? 'b' : 'w';
        return `${this.gridToPlacement()} ${turnChar} - - 0 1`;
    }

    syncFenDisplay() {
        const fenDisplay = document.getElementById('fen-display');
        if (fenDisplay) fenDisplay.value = this.currentFen();
    }

    buildPalette() {
        const palette = document.getElementById('piece-palette');
        if (!palette) return;
        palette.innerHTML = '';

        const pieces = ['K', 'Q', 'R', 'B', 'N', 'P', 'k', 'q', 'r', 'b', 'n', 'p'];
        pieces.forEach(piece => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-secondary palette-piece';
            btn.title = ChessUI.pieceLabel(piece);
            btn.dataset.piece = piece;
            btn.appendChild(ChessUI.createPieceElement(piece));
            btn.addEventListener('click', () => this.selectTool(piece, btn));
            palette.appendChild(btn);
        });

        const eraseBtn = document.createElement('button');
        eraseBtn.type = 'button';
        eraseBtn.className = 'btn btn-secondary palette-piece';
        eraseBtn.textContent = '🗑️ Borrar';
        eraseBtn.addEventListener('click', () => this.selectTool('erase', eraseBtn));
        palette.appendChild(eraseBtn);
    }

    selectTool(tool, btnEl) {
        document.querySelectorAll('.palette-piece').forEach(b => b.classList.remove('is-active'));
        if (this.selectedTool === tool) {
            this.selectedTool = null;
        } else {
            this.selectedTool = tool;
            btnEl.classList.add('is-active');
        }
        this.selectedSquare = null;
    }

    renderBoard() {
        this.boardEl.innerHTML = '';
        for (let r = 0; r < 8; r++) {
            for (let c = 0; c < 8; c++) {
                const fileChar = String.fromCharCode(97 + c);
                const rankNum = 8 - r;
                const squareName = `${fileChar}${rankNum}`;

                const squareEl = document.createElement('div');
                const isLight = (r + c) % 2 === 0;
                squareEl.className = `square ${isLight ? 'light' : 'dark'}`;
                squareEl.dataset.square = squareName;

                ChessUI.appendCoordinates(squareEl, { col: c, row: r, fileChar, rankNum });

                const piece = this.grid[r][c];
                if (piece) {
                    squareEl.appendChild(ChessUI.createPieceElement(piece));
                }

                squareEl.addEventListener('click', () => this.handleSquareClick(squareName, r, c));
                this.boardEl.appendChild(squareEl);
            }
        }
        if (this.selectedSquare) {
            const sqEl = this.boardEl.querySelector(`[data-square="${this.selectedSquare}"]`);
            if (sqEl) sqEl.classList.add('selected');
        }
    }

    handleSquareClick(squareName, r, c) {
        if (this.selectedTool) {
            this.grid[r][c] = (this.selectedTool === 'erase') ? null : this.selectedTool;
            this.renderBoard();
            this.syncFenDisplay();
            return;
        }

        // Move-mode: click a piece then click destination to relocate it.
        if (!this.selectedSquare) {
            if (this.grid[r][c]) {
                this.selectedSquare = squareName;
                this.selectedSquarePos = { r, c };
                this.renderBoard();
            }
            return;
        }

        if (this.selectedSquare === squareName) {
            this.selectedSquare = null;
            this.renderBoard();
            return;
        }

        const fromPos = this.selectedSquarePos;
        this.grid[r][c] = this.grid[fromPos.r][fromPos.c];
        this.grid[fromPos.r][fromPos.c] = null;
        this.selectedSquare = null;
        this.renderBoard();
        this.syncFenDisplay();
    }

    renderSolutionList() {
        const list = document.getElementById('solution-move-list');
        if (!list) return;
        list.innerHTML = '';
        this.solutionMoves.forEach((uci, idx) => {
            const li = document.createElement('li');
            li.style.marginBottom = '0.25rem';
            li.innerHTML = `<span style="font-family: monospace;">${uci}</span> `;
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-danger';
            removeBtn.style.cssText = 'padding: 0.1rem 0.5rem; font-size: 0.7rem; margin-left: 0.5rem;';
            removeBtn.textContent = 'Quitar';
            removeBtn.addEventListener('click', () => {
                this.solutionMoves.splice(idx, 1);
                this.renderSolutionList();
            });
            li.appendChild(removeBtn);
            list.appendChild(li);
        });
    }

    renderVariationList() {
        const list = document.getElementById('variation-list');
        if (!list) return;
        list.innerHTML = '';
        Object.keys(this.variations).forEach(ply => {
            (this.variations[ply] || []).forEach((uci, idx) => {
                const li = document.createElement('li');
                li.style.marginBottom = '0.25rem';
                li.innerHTML = `Ply ${ply}: <span style="font-family: monospace;">${uci}</span> `;
                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn btn-danger';
                removeBtn.style.cssText = 'padding: 0.1rem 0.5rem; font-size: 0.7rem; margin-left: 0.5rem;';
                removeBtn.textContent = 'Quitar';
                removeBtn.addEventListener('click', () => {
                    this.variations[ply].splice(idx, 1);
                    if (this.variations[ply].length === 0) delete this.variations[ply];
                    this.renderVariationList();
                });
                li.appendChild(removeBtn);
                list.appendChild(li);
            });
        });
    }

    renderHintList() {
        const list = document.getElementById('hint-list');
        if (!list) return;
        list.innerHTML = '';
        this.hints.forEach((hint, idx) => {
            const li = document.createElement('li');
            li.style.marginBottom = '0.25rem';
            li.textContent = `${hint} `;
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-danger';
            removeBtn.style.cssText = 'padding: 0.1rem 0.5rem; font-size: 0.7rem; margin-left: 0.5rem;';
            removeBtn.textContent = 'Quitar';
            removeBtn.addEventListener('click', () => {
                this.hints.splice(idx, 1);
                this.renderHintList();
            });
            li.appendChild(removeBtn);
            list.appendChild(li);
        });
    }

    initEvents() {
        document.getElementById('btn-reset-start').addEventListener('click', () => {
            this.grid = this.parsePlacement(STARTING_GRID_FEN);
            this.renderBoard();
            this.syncFenDisplay();
        });

        document.getElementById('btn-clear-board').addEventListener('click', () => {
            this.grid = Array.from({ length: 8 }, () => Array(8).fill(null));
            this.renderBoard();
            this.syncFenDisplay();
        });

        document.getElementById('btn-load-fen').addEventListener('click', () => {
            const fenDisplay = document.getElementById('fen-display');
            const parts = fenDisplay.value.trim().split(' ');
            if (parts.length < 1 || !parts[0].includes('/')) {
                alert('FEN inválido: falta la colocación de piezas.');
                return;
            }
            try {
                this.grid = this.parsePlacement(parts[0]);
            } catch (e) {
                alert('No se pudo interpretar el FEN.');
                return;
            }
            const sideSelect = document.getElementById('side_to_move');
            if (sideSelect && parts[1]) {
                sideSelect.value = parts[1] === 'b' ? 'BLACK' : 'WHITE';
            }
            this.renderBoard();
            this.syncFenDisplay();
        });

        document.getElementById('side_to_move').addEventListener('change', () => this.syncFenDisplay());

        document.getElementById('btn-add-solution-move').addEventListener('click', () => {
            const input = document.getElementById('solution-move-input');
            const value = input.value.trim().toLowerCase();
            if (!/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(value)) {
                alert('Formato UCI inválido. Ejemplo: e2e4 o e7e8q.');
                return;
            }
            this.solutionMoves.push(value);
            input.value = '';
            this.renderSolutionList();
        });

        document.getElementById('btn-add-variation').addEventListener('click', () => {
            const plyInput = document.getElementById('variation-ply-input');
            const moveInput = document.getElementById('variation-move-input');
            const ply = plyInput.value.trim();
            const value = moveInput.value.trim().toLowerCase();
            if (ply === '' || isNaN(parseInt(ply))) {
                alert('Indica el número de ply al que aplica la variante.');
                return;
            }
            if (!/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(value)) {
                alert('Formato UCI inválido. Ejemplo: e2e4 o e7e8q.');
                return;
            }
            if (!this.variations[ply]) this.variations[ply] = [];
            this.variations[ply].push(value);
            moveInput.value = '';
            this.renderVariationList();
        });

        document.getElementById('btn-add-hint').addEventListener('click', () => {
            const input = document.getElementById('hint-input');
            const value = input.value.trim();
            if (!value) return;
            this.hints.push(value);
            input.value = '';
            this.renderHintList();
        });

        document.getElementById('puzzle-form').addEventListener('submit', (e) => {
            document.getElementById('initial_fen').value = this.currentFen();
            document.getElementById('solution_moves').value = JSON.stringify(this.solutionMoves);
            document.getElementById('variations_json').value = JSON.stringify(this.variations);
            document.getElementById('hints').value = JSON.stringify(this.hints);
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.puzzleCreatorApp = new PuzzleCreatorApp();
});
