const isDev = !!(typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV);

type ArgList = any[];
const noop = (..._args: ArgList) => {};
const make = (fn: (...args: ArgList) => void, enabled: boolean) =>
  enabled ? fn.bind(console) : noop;

const logger = {
  debug: make(console.debug, isDev),
  info: make(console.info, true),
  warn: make(console.warn, true),
  error: make(console.error, true),
};

export default logger;
