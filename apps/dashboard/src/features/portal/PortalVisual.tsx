import styles from './Portal.module.css';
export function PortalVisual(){return <div className={styles.visual} aria-label="Illustration of the Dubai skyline and a connected research workflow">
  <div className={styles.visualHeading}><span>YOUR NEXT CHAPTER</span><strong>Built around Dubai.<br/>Connected by intelligence.</strong></div>
  <svg viewBox="0 0 580 480" fill="none" role="img" aria-label="Architectural skyline illustration"><defs><linearGradient id="cityLight" x1="290" y1="50" x2="290" y2="450" gradientUnits="userSpaceOnUse"><stop stopColor="#d7b77b"/><stop offset="1" stopColor="#596c78" stopOpacity=".1"/></linearGradient><linearGradient id="citySky" x1="0" x2="580"><stop stopColor="#172d3b"/><stop offset="1" stopColor="#0b1b2a"/></linearGradient></defs>
    <circle cx="355" cy="172" r="118" stroke="#d6b577" strokeOpacity=".16"/><circle cx="355" cy="172" r="151" stroke="#d6b577" strokeOpacity=".08"/>
    <path d="M20 400H560M20 430H560" stroke="#b1c0c7" strokeOpacity=".15"/>
    <path d="M46 400V290H96V400M57 300V380M69 300V380M82 300V380M116 400V250H159V400M127 261V380M144 261V380M179 400V213L220 188V400M190 225V380M205 216V380" stroke="url(#cityLight)" strokeWidth="2"/>
    <path d="M249 400V215H259V170H268V128H278V90H285V46H289V14H292V46H296V90H304V128H314V170H324V215H334V400Z" fill="url(#citySky)" stroke="#d7b77b" strokeWidth="2"/>
    <path d="M282 123V390M292 75V390M303 157V390M269 210V390M316 250V390" stroke="#d7b77b" strokeOpacity=".36"/>
    <path d="M357 400V286L383 230L408 286V400M368 297H396M368 320H396M368 344H396M368 369H396M427 400V251H468V400M438 263V386M455 263V386M491 400V309H538V400M503 321V386M525 321V386" stroke="url(#cityLight)" strokeWidth="2"/>
    <path d="M44 454C160 425 324 435 542 455" stroke="#d7b77b" strokeOpacity=".4"/>
  </svg>
  <div className={styles.visualFooter}><span className={styles.liveDot}/><span>Research. Review. Move forward.</span><span>01 — 03</span></div>
</div>;}
