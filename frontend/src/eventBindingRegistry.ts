import type { EventBinder } from "./controllers/core/eventBinder";

export class EventBindingRegistry {
	private readonly boundEventNames = new WeakMap<EventTarget, Set<string>>();


	public bind: EventBinder = (element: EventTarget | null, eventName: string, listener: EventListener, options?: AddEventListenerOptions): void => {
		if (!element) {
			return;
		}

		let eventNames = this.boundEventNames.get(element);
		if (!eventNames) {
			eventNames = new Set<string>();
			this.boundEventNames.set(element, eventNames);
		}

		if (eventNames.has(eventName)) {
			return;
		}

		eventNames.add(eventName);
		element.addEventListener(eventName, listener as EventListener, options);
	};
}
