import { useState } from 'react';
import { Infinity as InfinityIcon, Menu, X } from 'lucide-react';

const BG_VIDEO =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260511_230229_7c9bc431-46cf-489a-948d-e8144d8eb5d4.mp4';

const navLinks = [{ label: 'Home', active: true }, { label: 'Lead Finder' }];

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  const scrollToTool = () => {
    document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="relative w-full h-screen overflow-hidden">
      {/* Looping background video */}
      <video
        className="absolute inset-0 w-full h-full object-cover"
        autoPlay
        muted
        loop
        playsInline
        src={BG_VIDEO}
      />

      {/* Navbar */}
      <nav className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-5 sm:px-8 py-5">
        {/* Logo */}
        <div className="flex gap-2 text-white font-medium text-base items-center">
          <InfinityIcon size={22} strokeWidth={1.5} />
          <span>GapFinder</span>
        </div>

        {/* Nav pill (desktop) */}
        <div className="hidden md:flex liquid-glass items-center gap-1 rounded-xl px-2 py-2">
          {navLinks.map((link) => (
            <button
              key={link.label}
              onClick={link.label === 'Home' ? undefined : scrollToTool}
              className={`flex items-center gap-0.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                link.active
                  ? 'bg-white/15 text-white'
                  : 'text-white/70 hover:text-white'
              }`}
            >
              {link.label}
            </button>
          ))}
        </div>

        {/* CTA (desktop) */}
        <div className="hidden md:flex items-center gap-3">
          <button
            onClick={scrollToTool}
            className="bg-white text-black text-sm font-medium px-4 py-2.5 rounded-full hover:bg-white/90 transition-colors"
          >
            Find Leads
          </button>
        </div>

        {/* Mobile toggle */}
        <button
          className="md:hidden liquid-glass text-white p-2 rounded-lg"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {menuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </nav>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="absolute top-[72px] left-4 right-4 z-30 md:hidden liquid-glass rounded-2xl p-4 flex flex-col gap-1">
          {navLinks.map((link) => (
            <button
              key={link.label}
              onClick={() => {
                setMenuOpen(false);
                if (link.label !== 'Home') scrollToTool();
              }}
              className={`flex items-center justify-between w-full px-4 py-3 rounded-lg text-sm transition-colors ${
                link.active
                  ? 'bg-white/15 text-white'
                  : 'text-white/70 hover:text-white'
              }`}
            >
              <span className="flex items-center gap-0.5">
                {link.label}
              </span>
            </button>
          ))}
          <div className="flex gap-2 mt-2 pt-3 border-t border-white/10">
            <button
              onClick={() => {
                setMenuOpen(false);
                scrollToTool();
              }}
              className="flex-1 bg-white text-black text-sm font-medium px-4 py-2.5 rounded-full hover:bg-white/90 transition-colors"
            >
              Find Leads
            </button>
          </div>
        </div>
      )}

      {/* Hero content (bottom-left) */}
      <div className="absolute bottom-0 left-0 z-20 px-6 sm:px-12 pb-10 sm:pb-16 max-w-2xl">
        <h1 className="text-white text-4xl sm:text-5xl lg:text-6xl font-medium leading-tight tracking-tight mb-4">
          Find Gaps, Win Clients Every Day
        </h1>
        <p className="text-white/60 text-sm leading-relaxed mb-7 max-w-md">
          Take charge of your pipeline with live OpenStreetMap data — uncover
          local businesses missing websites, audit their presence, and reach
          verified emails with zero paid APIs.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={scrollToTool}
            className="bg-white text-black text-sm sm:text-base font-medium px-6 sm:px-7 py-3 rounded-full hover:bg-white/90 transition-colors"
          >
            Find Leads
          </button>
          <button
            onClick={scrollToTool}
            className="liquid-glass text-white text-sm sm:text-base font-medium px-6 sm:px-7 py-3 rounded-full hover:bg-white/5 transition-colors"
          >
            See How
          </button>
        </div>
      </div>
    </div>
  );
}
