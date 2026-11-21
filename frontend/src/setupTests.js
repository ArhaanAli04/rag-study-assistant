// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// The router-level tests render the whole app; on a busy CI runner the first test in such a
// file exceeded Jest's 5 s default (PR #6, run 42106368584) though nothing was waiting on time.
jest.setTimeout(15000);

// react-router 7 needs TextEncoder, which CRA's jsdom doesn't provide. Set here (before any test
// file's imports run) so components holding a <Link> can be tested with plain imports (Day 19).
const { TextDecoder, TextEncoder } = require('util');
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;
