import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useMediaQuery } from "../hooks/useMediaQuery.js";

/** Colunas por vez: duas em tela larga e uma em tela estreita (fonte única; o CSS lê o valor por variável). */
export const VISIBLE_WIDE = 2;
export const VISIBLE_NARROW = 1;
const NARROW_QUERY = "(max-width: 720px)";
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
// Duração do deslize (a mesma do CSS, em `--carousel-slide-ms`) e folga para o caso de o navegador não avisar o fim.
export const SLIDE_MS = 380;
const SLIDE_FALLBACK_MS = SLIDE_MS + 150;
const MAX_QUEUED_STEPS = 2; // cliques que chegam durante um deslize esperam a vez, sem acumular sem fim
// Passar o mouse sobre a seta avança depois de uma pausa (evita avanço por um simples atravessar) e segue enquanto ficar.
const HOVER_DELAY_MS = 600;
const HOVER_REPEAT_MS = 1000;

const CHEVRON = {
  prev: "M15 5l-7 7 7 7",
  next: "M9 5l7 7-7 7",
};

const mod = (value, size) => ((value % size) + size) % size;

/**
 * Seta lateral do carrossel. Clicar avança na hora; deixar o mouse em cima avança depois de `HOVER_DELAY_MS` e repete a
 * cada `HOVER_REPEAT_MS`. O clique avança uma vez e suspende o avanço por mouse parado até o mouse sair e voltar, então
 * "chegar e clicar", ou clicar e deixar o mouse ali, avança uma posição, não duas.
 * Só o ponteiro de mouse conta como "em cima": num toque só vale o clique. Ela é um botão, logo o teclado também a usa.
 */
function ArrowButton({ direction, label, onShift }) {
  const timer = useRef(null);

  const stop = useCallback(() => clearTimeout(timer.current), []);
  const schedule = useCallback(
    (delay) => {
      stop();
      timer.current = setTimeout(() => {
        onShift();
        schedule(HOVER_REPEAT_MS);
      }, delay);
    },
    [onShift, stop],
  );
  useEffect(() => stop, [stop]); // desmontar cancela o temporizador pendente

  return (
    <button
      type="button"
      className="secondary outline carousel-arrow"
      aria-label={label}
      title={label}
      onClick={() => {
        stop();
        onShift();
      }}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") schedule(HOVER_DELAY_MS);
      }}
      onPointerLeave={stop}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d={CHEVRON[direction]} />
      </svg>
    </button>
  );
}

/**
 * Carrossel infinito das colunas de saída: mostra `VISIBLE_WIDE` colunas por vez (`VISIBLE_NARROW` em tela estreita) e,
 * com mais itens que isso, setas laterais giram em ciclo (1 → 2 → 3 → 1...). Com menos itens, mostra todos, sem setas.
 *
 * O giro é um deslize de verdade: as colunas ficam numa faixa e, ao girar, a coluna que entra é montada fora da tela
 * (à direita ou à esquerda) e a faixa desliza uma posição com `transition`. Ao fim, a posição é confirmada e a faixa volta
 * a ter só as colunas visíveis; como cada coluna tem chave própria, o React mantém os elementos e nada pisca. Os itens
 * são desenhados por `render(item)` e o estado de cada coluna (notas) fica com quem usa, então girar não perde nada.
 * Com "reduzir movimento" o giro é imediato. Para recomeçar na primeira posição, quem usa troca a `key`.
 * `getKey(item)` e `getLabel(item)` dão a chave do item e o nome da legenda "Mostrando ...".
 */
export default function VersionCarousel({ items, getKey, getLabel, render, label }) {
  const visibleCount = useMediaQuery(NARROW_QUERY) ? VISIBLE_NARROW : VISIBLE_WIDE;
  const reducedMotion = useMediaQuery(REDUCED_MOTION_QUERY);
  const total = items.length;
  const infinite = total > visibleCount;

  const [start, setStart] = useState(0);
  const [move, setMove] = useState(null); // { step: +1 | -1, running: boolean } enquanto desliza
  const active = useRef(null); // o mesmo que `move`, legível nos temporizadores sem depender do render
  const queue = useRef([]);
  const fallback = useRef(null);
  const finishRef = useRef(null); // `begin` e `finish` se chamam: a ref evita a dependência circular

  const begin = useCallback(
    (step) => {
      if (reducedMotion) {
        setStart((current) => mod(current + step, total));
        return;
      }
      active.current = { step };
      setMove({ step, running: false });
      // Dois quadros com a coluna nova já posicionada, só então liga a transição: sem isso o navegador não anima.
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          if (active.current?.step === step) setMove({ step, running: true });
        }),
      );
      clearTimeout(fallback.current);
      fallback.current = setTimeout(() => finishRef.current?.(), SLIDE_FALLBACK_MS);
    },
    [reducedMotion, total],
  );

  const finish = useCallback(() => {
    const current = active.current;
    if (!current) return;
    clearTimeout(fallback.current);
    active.current = null;
    setStart((value) => mod(value + current.step, total));
    setMove(null);
    const nextStep = queue.current.shift();
    if (nextStep) begin(nextStep);
  }, [begin, total]);
  finishRef.current = finish;

  useEffect(() => () => clearTimeout(fallback.current), []);

  const shift = useCallback(
    (step) => {
      if (active.current) {
        if (queue.current.length < MAX_QUEUED_STEPS) queue.current.push(step);
        return;
      }
      begin(step);
    },
    [begin],
  );
  const next = useCallback(() => shift(1), [shift]);
  const prev = useCallback(() => shift(-1), [shift]);

  const position = infinite ? start % total : 0;
  const slots = infinite ? visibleCount + (move ? 1 : 0) : total;
  const first = position + (move && move.step < 0 ? -1 : 0);
  const shown = infinite ? Array.from({ length: slots }, (_, index) => items[mod(first + index, total)]) : items;
  // Quantas colunas a faixa está deslocada: avançar sai de 0 para 1, voltar sai de 1 para 0 (a nova coluna entra à esquerda).
  const offset = !move ? 0 : move.step > 0 ? (move.running ? 1 : 0) : move.running ? 0 : 1;
  const captionItems = infinite ? Array.from({ length: visibleCount }, (_, index) => items[mod(position + index, total)]) : [];

  return (
    <section
      className="carousel"
      data-infinite={infinite}
      aria-roledescription="carrossel"
      aria-label={label}
      style={{ "--carousel-visible": visibleCount, "--carousel-slide-ms": `${SLIDE_MS}ms` }}
    >
      {infinite && (
        <p className="hint carousel-caption" aria-live="polite">
          Mostrando {captionItems.map(getLabel).join(" e ")} de {total}
        </p>
      )}
      {infinite && <ArrowButton direction="prev" label="Versões anteriores" onShift={prev} />}
      <div className="carousel-viewport">
        <div
          className="carousel-track"
          data-running={Boolean(move?.running)}
          style={{ "--carousel-offset": offset }}
          onTransitionEnd={(event) => {
            if (event.target === event.currentTarget && event.propertyName === "transform") finish();
          }}
        >
          {shown.map((item) => (
            <Fragment key={getKey(item)}>{render(item)}</Fragment>
          ))}
        </div>
      </div>
      {infinite && <ArrowButton direction="next" label="Próximas versões" onShift={next} />}
    </section>
  );
}
