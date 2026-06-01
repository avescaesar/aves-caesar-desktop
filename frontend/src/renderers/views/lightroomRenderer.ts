import { iconPlug } from "../../icons";
import type { LightroomState } from "../../state/lightroomState";
import { escapeHtml } from "../../utils";
import type { RendererContext } from "../rendererContext";

export class LightroomRenderer {
	public constructor(private readonly context: RendererContext, private readonly lightroom: LightroomState) {}


	public render(): string {
		const info = this.lightroom.info;
		const plugin = info?.plugin;
		const pluginStatus = plugin?.installed ? this.context.text("lightroom.pluginInstalled") : this.context.text("lightroom.pluginNotInstalled");
		const installedVersion = plugin?.installed ? this.renderLightroomVersion(plugin.installedVersion) : pluginStatus;
		const availableVersion = this.renderLightroomVersion(plugin?.availableVersion);
		return `
		<section class="lightroom-view">
			<div class="section-heading">
				<div class="section-title">
					<h2>${this.context.text("lightroom.title")}</h2>
				</div>
			</div>
			<section class="lightroom-grid">
				<article class="lightroom-panel">
					<h3>${this.context.text("lightroom.plugin")}</h3>
					<div class="lightroom-status"><strong>${pluginStatus}</strong></div>
					<div class="lightroom-versions">
						<div>
							<span>${this.context.text("lightroom.installedVersion")}</span>
							<strong>${installedVersion}</strong>
						</div>
						<div>
							<span>${this.context.text("lightroom.availableVersion")}</span>
							<strong>${availableVersion}</strong>
						</div>
					</div>
					<div class="lightroom-actions">
						<button id="installLightroomPlugin" class="toolbar-button is-primary" type="button" ${this.lightroom.busy ? "disabled" : ""}>${iconPlug()}<span>${this.context.text("lightroom.install")}</span></button>
						${plugin?.installed ? `<button id="uninstallLightroomPlugin" class="secondary-action" type="button" ${this.lightroom.busy ? "disabled" : ""}>${iconPlug()}<span>${this.context.text("lightroom.uninstall")}</span></button>` : ""}
					</div>
				</article>
				<article class="lightroom-panel">
					<h3>${this.context.text("lightroom.aboutTitle")}</h3>
					<p>${this.context.text("lightroom.aboutBody")}</p>
					<p>${this.context.text("lightroom.aboutMenu")}</p>
					<p>${this.context.text("lightroom.aboutSafety")}</p>
				</article>
			</section>
			${this.lightroom.message ? `<p class="lightroom-message">${escapeHtml(this.lightroom.message)}</p>` : ""}
		</section>
	`;
	}


	private renderLightroomVersion(version: string | null | undefined): string {
		return version ? `v${escapeHtml(version)}` : this.context.text("common.unknown");
	}
}
