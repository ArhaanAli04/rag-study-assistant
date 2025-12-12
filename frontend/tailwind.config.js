/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0F0F0F',
        foreground: '#FFFFFF',
        card: '#1F2937',
        border: '#374151',
        input: '#1F2937',
        primary: '#7C3AED',
        secondary: '#1F2937',
        muted: '#9CA3AF',
        accent: '#3B82F6',
        destructive: '#EF4444',
        success: '#10B981',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'pulse-dot': 'pulse 1.4s ease-in-out infinite',
        'slide-down': 'slideDown 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        pulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
        slideDown: {
          from: { opacity: '0', maxHeight: '0' },
          to: { opacity: '1', maxHeight: '500px' },
        },
      },
    },
  },
  plugins: [],
}
