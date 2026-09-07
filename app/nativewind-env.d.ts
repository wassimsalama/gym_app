/// <reference types="nativewind/types" />

// TypeScript 6 rejects side-effect imports it has no declaration for; Metro
// resolves this one through nativewind's PostCSS transform.
declare module '*.css';
