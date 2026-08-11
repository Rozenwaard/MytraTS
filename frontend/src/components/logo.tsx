export function Logo() {
  return (
    <div className="w-9 h-9 bg-accent rounded-lg flex items-center justify-center mr-2 text-base-100 flex-shrink-0">
      <span className="flex items-center -translate-x-[8px]">
        {[0, 1, 2].map((i) => (
          <svg
            key={i}
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-6 h-6"
            style={{ transform: "scale(0.6, 1.1)", marginRight: -17, display: "inline-block" }}
          >
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
        ))}
      </span>
    </div>
  );
}
