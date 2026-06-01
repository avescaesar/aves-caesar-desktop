import "./scss/styles.scss";
import { AvesCaesarApp } from "./app";

const appElement = document.querySelector<HTMLDivElement>("#app");
if (!appElement) {
	throw new Error("App root missing");
}

void new AvesCaesarApp(appElement).start();
