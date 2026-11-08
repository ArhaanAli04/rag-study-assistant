// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// The router-level tests render the whole app; on a busy CI runner the first test in such a
// file exceeded Jest's 5 s default (PR #6, run 42106368584) though nothing was waiting on time.
jest.setTimeout(15000);
