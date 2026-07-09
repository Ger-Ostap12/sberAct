// Браузерная сборка mammoth не имеет собственной декларации — типы у неё
// те же, что у основного модуля (CommonJS export=).
declare module 'mammoth/mammoth.browser' {
  import mammoth = require('mammoth');
  export = mammoth;
}
