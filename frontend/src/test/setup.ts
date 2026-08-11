import "@testing-library/jest-dom/vitest";

Object.defineProperty(Element.prototype, "scrollIntoView", {
  configurable: true,
  value: () => undefined,
});

globalThis.requestAnimationFrame = (callback: FrameRequestCallback) => {
  callback(0);
  return 0;
};
