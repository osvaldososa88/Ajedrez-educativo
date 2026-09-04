/**
 * Presentación compartida del tablero: piezas SVG y utilidades visuales.
 * No calcula movimientos legales; solo renderiza lo que el servidor ya validó.
 */
(function (global) {
    const FILE_MAP = { k: 'K', q: 'Q', r: 'R', b: 'B', n: 'N', p: 'P' };

    const LABELS = {
        K: 'Rey blanco', Q: 'Dama blanca', R: 'Torre blanca',
        B: 'Alfil blanco', N: 'Caballo blanco', P: 'Peón blanco',
        k: 'Rey negro', q: 'Dama negra', r: 'Torre negra',
        b: 'Alfil negro', n: 'Caballo negro', p: 'Peón negro'
    };

    function pieceBase() {
        if (typeof global.CHESS_PIECE_BASE === 'string' && global.CHESS_PIECE_BASE) {
            return global.CHESS_PIECE_BASE.endsWith('/')
                ? global.CHESS_PIECE_BASE
                : `${global.CHESS_PIECE_BASE}/`;
        }
        return '/static/img/pieces/';
    }

    const ChessUI = {
        pieceSrc(fenChar) {
            const color = fenChar === fenChar.toUpperCase() ? 'w' : 'b';
            const type = FILE_MAP[fenChar.toLowerCase()];
            if (!type) return '';
            return `${pieceBase()}${color}${type}.svg`;
        },

        pieceLabel(fenChar) {
            return LABELS[fenChar] || 'Pieza';
        },

        createPieceElement(fenChar, options = {}) {
            const wrap = document.createElement('span');
            wrap.className = 'piece';
            wrap.dataset.fen = fenChar;

            const img = document.createElement('img');
            img.className = 'piece-img';
            img.src = this.pieceSrc(fenChar);
            img.alt = this.pieceLabel(fenChar);
            img.draggable = true;
            wrap.appendChild(img);

            if (options.onDragStart) {
                img.addEventListener('dragstart', (e) => {
                    options.onDragStart(e, fenChar);
                });
            }

            return wrap;
        },

        parseFenPlacement(fen) {
            const position = (fen || '').split(' ')[0];
            const grid = [];
            const rows = position.split('/');
            for (let r = 0; r < 8; r++) {
                const row = [];
                const cells = rows[r] || '';
                for (let c = 0; c < cells.length; c++) {
                    const char = cells[c];
                    if (char >= '1' && char <= '8') {
                        const emptyCount = parseInt(char, 10);
                        for (let e = 0; e < emptyCount; e++) row.push(null);
                    } else {
                        row.push(char);
                    }
                }
                while (row.length < 8) row.push(null);
                grid.push(row.slice(0, 8));
            }
            return grid;
        },

        fenSideToMove(fen) {
            const parts = (fen || '').split(' ');
            return parts[1] === 'b' ? 'black' : 'white';
        },

        findKingSquare(grid, color) {
            const needle = color === 'white' ? 'K' : 'k';
            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    if (grid[r][c] === needle) {
                        return `${String.fromCharCode(97 + c)}${8 - r}`;
                    }
                }
            }
            return null;
        },

        squaresFromUci(uci) {
            if (!uci || uci.length < 4) return null;
            return { from: uci.slice(0, 2), to: uci.slice(2, 4) };
        },

        appendCoordinates(squareEl, { col, row, fileChar, rankNum }) {
            if (col === 0) {
                const rankCoord = document.createElement('span');
                rankCoord.className = 'coord coord-rank';
                rankCoord.textContent = String(rankNum);
                squareEl.appendChild(rankCoord);
            }
            if (row === 7) {
                const fileCoord = document.createElement('span');
                fileCoord.className = 'coord coord-file';
                fileCoord.textContent = fileChar;
                squareEl.appendChild(fileCoord);
            }
        },

        paintPromotionChoices(root, color) {
            if (!root) return;
            const isWhite = color !== 'black';
            root.querySelectorAll('.promotion-choice').forEach((choice) => {
                const piece = choice.getAttribute('data-piece') || 'q';
                const fenChar = isWhite ? piece.toUpperCase() : piece.toLowerCase();
                choice.replaceChildren();
                choice.appendChild(this.createPieceElement(fenChar));
            });
        },

        applyLastMove(boardEl, uci) {
            const squares = this.squaresFromUci(uci);
            if (!squares || !boardEl) return;
            const fromEl = boardEl.querySelector(`[data-square="${squares.from}"]`);
            const toEl = boardEl.querySelector(`[data-square="${squares.to}"]`);
            if (fromEl) fromEl.classList.add('last-move');
            if (toEl) toEl.classList.add('last-move');
        },

        applyCheck(boardEl, grid, fen, { isCheck, isCheckmate }) {
            if (!isCheck && !isCheckmate) return;
            const side = this.fenSideToMove(fen);
            const kingSq = this.findKingSquare(grid, side);
            if (!kingSq) return;
            const kingEl = boardEl.querySelector(`[data-square="${kingSq}"]`);
            if (!kingEl) return;
            kingEl.classList.add(isCheckmate ? 'in-checkmate' : 'in-check');
        },

        applyLegalHints(boardEl, fromSquare, legalMoves, grid) {
            if (!fromSquare || !legalMoves) return;
            legalMoves
                .filter((m) => m.from === fromSquare)
                .forEach((m) => {
                    const targetEl = boardEl.querySelector(`[data-square="${m.to}"]`);
                    if (!targetEl) return;
                    const file = m.to.charCodeAt(0) - 97;
                    const rank = 8 - parseInt(m.to[1], 10);
                    const occupant = grid[rank] && grid[rank][file];
                    if (occupant) {
                        targetEl.classList.add('legal-capture');
                    } else {
                        targetEl.classList.add('legal-move');
                    }
                });
        },

        animateMovedPiece(boardEl, uci) {
            const squares = this.squaresFromUci(uci);
            if (!squares || !boardEl) return;
            const fromEl = boardEl.querySelector(`[data-square="${squares.from}"]`);
            const toEl = boardEl.querySelector(`[data-square="${squares.to}"]`);
            const piece = toEl && toEl.querySelector('.piece');
            if (!fromEl || !toEl || !piece) return;

            const fromBox = fromEl.getBoundingClientRect();
            const toBox = toEl.getBoundingClientRect();
            const dx = fromBox.left - toBox.left;
            const dy = fromBox.top - toBox.top;
            if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;

            piece.classList.add('piece-animating');
            piece.style.transform = `translate(${dx}px, ${dy}px)`;
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    piece.style.transform = 'translate(0, 0)';
                });
            });
            const clear = () => {
                piece.classList.remove('piece-animating');
                piece.style.transform = '';
                piece.removeEventListener('transitionend', clear);
            };
            piece.addEventListener('transitionend', clear);
            setTimeout(clear, 220);
        },

        renderFEN(container, fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1') {
            if (!container) return;
            container.innerHTML = '';
            const grid = this.parseFenPlacement(fen);
            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    const sq = document.createElement('div');
                    const isLight = (r + c) % 2 === 0;
                    const fileChar = String.fromCharCode(97 + c);
                    const rankNum = 8 - r;
                    sq.className = `square ${isLight ? 'light' : 'dark'}`;
                    sq.dataset.square = `${fileChar}${rankNum}`;
                    const piece = grid[r][c];
                    if (piece) {
                        sq.appendChild(this.createPieceElement(piece));
                    }
                    this.appendCoordinates(sq, { col: c, row: r, fileChar, rankNum });
                    container.appendChild(sq);
                }
            }
        }
    };

    global.ChessUI = ChessUI;
})(window);
