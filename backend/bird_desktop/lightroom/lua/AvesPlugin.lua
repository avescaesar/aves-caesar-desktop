local LrApplication = import 'LrApplication'
local LrBinding = import 'LrBinding'
local LrDialogs = import 'LrDialogs'
local LrFunctionContext = import 'LrFunctionContext'
local LrHttp = import 'LrHttp'
local LrProgressScope = import 'LrProgressScope'
local LrTasks = import 'LrTasks'
local LrView = import 'LrView'

local Aves = {}
local BASE_URL = '__AVES_LIGHTROOM_BASE_URL__'
local PLUGIN_VERSION = '1.0.20'
local KEYWORD_ROOT = 'Aves Caesar'

local json = {}

function json.escape(value)
    value = string.gsub(value, '\\', '\\\\')
    value = string.gsub(value, '"', '\\"')
    value = string.gsub(value, '\n', '\\n')
    value = string.gsub(value, '\r', '\\r')
    value = string.gsub(value, '\t', '\\t')
    return value
end

function json.encode(value)
    local value_type = type(value)
    if value_type == 'nil' then
        return 'null'
    end

    if value_type == 'boolean' then
        return value and 'true' or 'false'
    end

    if value_type == 'number' then
        return tostring(value)
    end

    if value_type == 'string' then
        return '"' .. json.escape(value) .. '"'
    end

    local is_array = true
    local max_index = 0
    for key, _ in pairs(value) do
        if type(key) ~= 'number' then
            is_array = false
            break
        end

        if key > max_index then
            max_index = key
        end
    end

    local parts = {}
    if is_array then
        for index = 1, max_index do
            table.insert(parts, json.encode(value[index]))
        end

        return '[' .. table.concat(parts, ',') .. ']'
    end

    for key, item in pairs(value) do
        table.insert(parts, json.encode(tostring(key)) .. ':' .. json.encode(item))
    end

    return '{' .. table.concat(parts, ',') .. '}'
end

function json.decode(value)
    local position = 1

    local function skip_space()
        while true do
            local char = string.sub(value, position, position)
            if char ~= ' ' and char ~= '\n' and char ~= '\r' and char ~= '\t' then
                return
            end

            position = position + 1
        end
    end

    local function parse_string()
        position = position + 1
        local result = ''
        while position <= string.len(value) do
            local char = string.sub(value, position, position)
            if char == '"' then
                position = position + 1
                return result
            end

            if char == '\\' then
                local next_char = string.sub(value, position + 1, position + 1)
                if next_char == 'n' then
                    result = result .. '\n'
                elseif next_char == 'r' then
                    result = result .. '\r'
                elseif next_char == 't' then
                    result = result .. '\t'
                else
                    result = result .. next_char
                end

                position = position + 2
            else
                result = result .. char
                position = position + 1
            end
        end

        return result
    end

    local parse_value

    local function parse_array()
        position = position + 1
        local result = {}
        skip_space()
        if string.sub(value, position, position) == ']' then
            position = position + 1
            return result
        end

        while true do
            table.insert(result, parse_value())
            skip_space()
            local char = string.sub(value, position, position)
            position = position + 1
            if char == ']' then
                return result
            end
        end
    end

    local function parse_object()
        position = position + 1
        local result = {}
        skip_space()
        if string.sub(value, position, position) == '}' then
            position = position + 1
            return result
        end

        while true do
            skip_space()
            local key = parse_string()
            skip_space()
            position = position + 1
            result[key] = parse_value()
            skip_space()
            local char = string.sub(value, position, position)
            position = position + 1
            if char == '}' then
                return result
            end
        end
    end

    local function parse_number()
        local start = position
        while string.find(string.sub(value, position, position), '[0-9%.%-]') do
            position = position + 1
        end

        return tonumber(string.sub(value, start, position - 1))
    end

    function parse_value()
        skip_space()
        local char = string.sub(value, position, position)
        if char == '"' then
            return parse_string()
        end

        if char == '{' then
            return parse_object()
        end

        if char == '[' then
            return parse_array()
        end

        if string.sub(value, position, position + 3) == 'true' then
            position = position + 4
            return true
        end

        if string.sub(value, position, position + 4) == 'false' then
            position = position + 5
            return false
        end

        if string.sub(value, position, position + 3) == 'null' then
            position = position + 4
            return nil
        end

        return parse_number()
    end

    return parse_value()
end

local function request_json(method, path, body)
    local url = BASE_URL .. path
    local response = nil
    local headers = { { field = 'Content-Type', value = 'application/json' } }
    if method == 'POST' then
        response = LrHttp.post(url, json.encode(body or {}), headers)
    else
        response = LrHttp.get(url)
    end

    if response == nil or response == '' then
        error('Aves is not responding. Open Aves Caesar and try again.')
    end

    return json.decode(response)
end

local function client_log(job_id, payload)
    if job_id == nil or job_id == '' then
        return
    end

    pcall(function()
        request_json('POST', '/jobs/' .. job_id .. '/client-log', payload)
    end)
end

local function traceback_text(message)
    if debug ~= nil and debug.traceback ~= nil then
        return debug.traceback(tostring(message), 2)
    end

    return tostring(message)
end

local function report_plugin_error(job_id, message)
    client_log(job_id, {
        operation = 'plugin_unhandled_error',
        message = tostring(message),
        traceback = traceback_text(message),
    })
end

local function photo_path(photo)
    return photo:getRawMetadata('path')
end

local function unique_photos(photos)
    local seen = {}
    local result = {}
    for _, photo in ipairs(photos) do
        local path = photo_path(photo)
        if path ~= nil and seen[path] ~= true then
            seen[path] = true
            table.insert(result, photo)
        end
    end
    return result
end

local function active_folder_photos(catalog, include_children)
    local sources = catalog:getActiveSources()
    local photos = {}
    for _, source in ipairs(sources) do
        if type(source) ~= 'table' or source:type() ~= 'LrFolder' then
            return nil
        end

        local folder_photos = source:getPhotos(include_children)
        for _, photo in ipairs(folder_photos) do
            table.insert(photos, photo)
        end
    end

    return unique_photos(photos)
end

local function photos_for_mode(catalog, mode, include_children)
    if mode == 'selected' then
        return unique_photos(catalog:getTargetPhotos())
    end

    if mode == 'active_folder' then
        return active_folder_photos(catalog, include_children)
    end

    return unique_photos(catalog:getAllPhotos())
end

local function panel_action_button(factory, title, description, result)
    return factory:row {
        spacing = factory:control_spacing(),
        factory:push_button {
            title = title,
            width = 170,
            action = function(button)
                LrDialogs.stopModalWithResult(button, result)
            end,
        },
        factory:static_text {
            title = description,
            width = 360,
            height_in_lines = 2,
        },
    }
end

local function present_action_panel()
    return LrFunctionContext.callWithContext('avesActionPanel', function()
        local factory = LrView.osFactory()
        local rows = {
            spacing = factory:control_spacing(),
            factory:static_text {
                title = 'Aves Caesar',
                font = '<system/bold>',
            },
            factory:static_text {
                title = 'Choose what Aves should do in the current Lightroom catalog.',
                width = 560,
            },
            factory:spacer { height = 8 },
            factory:static_text {
                title = 'Prediction',
                font = '<system/bold>',
            },
            factory:separator { fill_horizontal = 1 },
            panel_action_button(factory, 'Tag selected photos', 'Predict birds for the currently selected photos, then apply Aves Caesar keywords.', 'tag_selected'),
            panel_action_button(factory, 'Tag active folder', 'Predict birds for photos in the active folder, with an option to include subfolders.', 'tag_active_folder'),
            panel_action_button(factory, 'Tag entire catalog...', 'Predict birds for every photo in the catalog. A confirmation is shown before starting.', 'tag_entire_catalog'),
            factory:spacer { height = 10 },
            factory:static_text {
                title = 'Maintenance',
                font = '<system/bold>',
            },
            factory:separator { fill_horizontal = 1 },
            panel_action_button(factory, 'Clear active folder...', 'Remove Aves Caesar-managed keywords from photos in the active folder.', 'clear_active_folder'),
            panel_action_button(factory, 'Clear entire catalog...', 'Remove Aves Caesar-managed keywords from the whole catalog after confirmation.', 'clear_entire_catalog'),
        }

        return LrDialogs.presentModalDialog {
            title = 'Aves Caesar',
            contents = factory:column(rows),
            actionVerb = 'Close',
            cancelVerb = '< exclude >',
        }
    end)
end

local function present_options(mode, count)
    return LrFunctionContext.callWithContext('avesOptions', function(context)
        local properties = LrBinding.makePropertyTable(context)
        properties.language = 'fr'
        properties.reprocess = false
        properties.includeChildren = true
        properties.gpxPaths = {}
        properties.gpxPathText = ''
        local factory = LrView.osFactory()
        local rows = {
            factory:static_text {
                title = 'Prediction',
                font = '<system/bold>',
            },
            factory:separator { fill_horizontal = 1 },
            factory:row {
                spacing = factory:control_spacing(),
                factory:static_text { title = 'Language', alignment = 'right', width = 140 },
                factory:popup_menu {
                    value = LrView.bind('language'),
                    width = 140,
                    items = {
                        { title = 'Francais', value = 'fr' },
                        { title = 'English', value = 'en' },
                    },
                },
            },
            factory:row {
                spacing = factory:control_spacing(),
                factory:static_text { title = '', width = 140 },
                factory:checkbox { title = 'Reprocess', value = LrView.bind('reprocess') },
            },
            factory:spacer { height = 10 },
            factory:static_text {
                title = 'Location fallback',
                font = '<system/bold>',
            },
            factory:separator { fill_horizontal = 1 },
            factory:static_text {
                title = 'Aves first uses GPS coordinates embedded in each photo. If a photo has no GPS coordinates, select a GPX track here and Aves will use it as a fallback for better accuracy.',
                width = 540,
                height_in_lines = 2,
            },
            factory:row {
                spacing = factory:control_spacing(),
                factory:static_text { title = 'GPX tracks', alignment = 'right', width = 140 },
                factory:edit_field { value = LrView.bind('gpxPathText'), width_in_chars = 48, enabled = false },
                factory:push_button {
                    title = 'Choose...',
                    action = function()
                        local selection = LrDialogs.runOpenPanel {
                            title = 'Select GPX file',
                            canChooseFiles = true,
                            canChooseDirectories = false,
                            allowsMultipleSelection = true,
                            fileTypes = { 'gpx' },
                        }
                        if selection ~= nil then
                            properties.gpxPaths = selection
                            if #selection == 1 then
                                properties.gpxPathText = selection[1]
                            elseif #selection > 1 then
                                properties.gpxPathText = tostring(#selection) .. ' GPX files selected'
                            end
                        end
                    end,
                },
            },
        }

        if mode == 'active_folder' then
            table.insert(rows, factory:spacer { height = 10 })
            table.insert(rows, factory:static_text {
                title = 'Folder scope',
                font = '<system/bold>',
            })
            table.insert(rows, factory:separator { fill_horizontal = 1 })
            table.insert(rows, factory:row {
                spacing = factory:control_spacing(),
                factory:static_text { title = '', width = 140 },
                factory:checkbox { title = 'Include subfolders', value = LrView.bind('includeChildren') },
            })
        end

        table.insert(rows, factory:spacer { height = 10 })
        table.insert(rows, factory:static_text {
            title = 'Run summary',
            font = '<system/bold>',
        })
        table.insert(rows, factory:separator { fill_horizontal = 1 })
        table.insert(rows, factory:static_text {
            title = tostring(count) .. ' photo(s) will be sent to Aves.',
            width = 540,
        })
        rows.bind_to_object = properties
        local result = LrDialogs.presentModalDialog {
            title = 'Aves Caesar',
            contents = factory:column(rows),
            actionVerb = 'Start',
        }

        if result ~= 'ok' then
            return nil
        end

        return {
            language = properties.language,
            reprocess = properties.reprocess == true,
            includeChildren = properties.includeChildren == true,
            gpxPaths = properties.gpxPaths,
        }
    end)
end

local function keyword_name(keyword)
    return keyword:getName()
end

local function keyword_parent(keyword)
    return keyword:getParent()
end

local function keyword_children(keyword)
    return keyword:getChildren() or {}
end

local function is_aves_keyword(keyword)
    if type(keyword) ~= 'table' then
        return false
    end

    local current = keyword
    while current ~= nil do
        if keyword_name(current) == KEYWORD_ROOT then
            return true
        end

        current = keyword_parent(current)
    end

    return false
end

local function collect_keyword_tree(keyword, result)
    table.insert(result, keyword)
    for _, child in ipairs(keyword_children(keyword)) do
        collect_keyword_tree(child, result)
    end
end

local function aves_managed_keywords(catalog)
    local keywords = catalog:getKeywords() or {}

    for _, keyword in ipairs(keywords) do
        if keyword_name(keyword) == KEYWORD_ROOT then
            local result = {}
            collect_keyword_tree(keyword, result)
            return result
        end
    end

    return {}
end

local function remove_aves_keywords(photo, managed_keywords)
    local managed = {}
    for _, keyword in ipairs(managed_keywords or {}) do
        managed[keyword] = true
    end

    local removed = 0
    for _, keyword in ipairs(photo:getRawMetadata('keywords') or {}) do
        if managed[keyword] == true then
            photo:removeKeyword(keyword)
            removed = removed + 1
        end
    end

    return removed
end

local function photo_has_aves_keyword(photo)
    for _, keyword in ipairs(photo:getRawMetadata('keywords') or {}) do
        if is_aves_keyword(keyword) then
            return true
        end
    end

    return false
end

local function photos_without_aves_keywords(photos)
    local result = {}
    local skipped = 0
    for _, photo in ipairs(photos) do
        if photo_has_aves_keyword(photo) then
            skipped = skipped + 1
        else
            table.insert(result, photo)
        end
    end

    return result, skipped
end

local function split_keyword_path(path)
    local parts = {}
    for part in string.gmatch(path, '[^|]+') do
        table.insert(parts, part)
    end
    return parts
end

local function find_root_keyword(catalog, name)
    local keywords = catalog:getKeywords() or {}

    for _, keyword in ipairs(keywords) do
        if keyword_name(keyword) == name and keyword_parent(keyword) == nil then
            return keyword
        end
    end

    return nil
end

local function find_child_keyword(parent, name)
    for _, child in ipairs(keyword_children(parent)) do
        if keyword_name(child) == name then
            return child
        end
    end

    return nil
end

local function ensure_keyword(catalog, name, parent)
    local existing = nil
    if parent == nil then
        existing = find_root_keyword(catalog, name)
    else
        existing = find_child_keyword(parent, name)
    end

    if existing ~= nil then
        return existing
    end

    return catalog:createKeyword(name, {}, parent ~= nil, parent, false)
end

local function find_keyword_path(catalog, path)
    local parent = nil
    local keyword = nil
    local parts = split_keyword_path(path)
    if #parts <= 1 then
        return nil, ''
    end

    for _, part in ipairs(parts) do
        local found_keyword = nil
        if parent == nil then
            found_keyword = find_root_keyword(catalog, part)
        else
            found_keyword = find_child_keyword(parent, part)
        end

        if found_keyword == nil then
            return nil, 'Keyword does not exist after creation: "' .. tostring(part) .. '"'
        end

        keyword = found_keyword
        parent = keyword
    end

    if keyword ~= nil then
        if not is_aves_keyword(keyword) then
            return nil, 'Keyword is not under ' .. KEYWORD_ROOT .. ' after creation: ' .. tostring(path)
        end
    end

    return keyword, ''
end

local function ensure_keyword_path(catalog, path)
    local parts = split_keyword_path(path)
    if #parts <= 1 then
        return true, ''
    end

    local parent = nil
    for index, part in ipairs(parts) do
        local existing = nil
        if parent == nil then
            existing = find_root_keyword(catalog, part)
        else
            existing = find_child_keyword(parent, part)
        end

        if existing == nil then
            local create_ok, create_result = LrTasks.pcall(function()
                return catalog:withWriteAccessDo('Create Aves Caesar keyword', function()
                    ensure_keyword(catalog, part, parent)
                end)
            end)
            if not create_ok then
                return false, tostring(create_result)
            end
        end

        local resolved = nil
        if parent == nil then
            resolved = find_root_keyword(catalog, part)
        else
            resolved = find_child_keyword(parent, part)
        end

        if resolved == nil then
            return false, 'Keyword still missing after create transaction: "' .. tostring(part) .. '"'
        end

        parent = resolved
    end

    return true, ''
end

local function apply_keyword_path(catalog, photo, path)
    local keyword, message = find_keyword_path(catalog, path)
    if keyword == nil then
        if message == '' then
            return true, ''
        end

        return false, message
    end

    photo:addKeyword(keyword)
    return true, ''
end

local function dedupe_keywords(keywords)
    local result = {}
    local seen = {}
    for _, keyword in ipairs(keywords or {}) do
        if seen[keyword] ~= true then
            seen[keyword] = true
            table.insert(result, keyword)
        end
    end
    return result
end

local function format_duration(seconds)
    seconds = math.floor(tonumber(seconds) or 0)
    local hours = math.floor(seconds / 3600)
    local minutes = math.floor((seconds % 3600) / 60)
    local remaining_seconds = seconds % 60
    local function two_digits(value)
        local number = math.floor(tonumber(value) or 0)
        if number < 10 then
            return '0' .. tostring(number)
        end

        return tostring(number)
    end

    return two_digits(hours) .. ':' .. two_digits(minutes) .. ':' .. two_digits(remaining_seconds)
end

local function numeric_value(value, fallback)
    local number = tonumber(value)
    if number == nil then
        return fallback
    end

    return number
end

local function update_progress(job_id, progress, completed, total, caption)
    local completed_number = numeric_value(completed, 0)
    local total_number = numeric_value(total, 1)
    if total_number <= 0 then
        total_number = 1
    end

    local portion_ok, portion_message = pcall(function()
        progress:setPortionComplete(completed_number, total_number)
    end)
    if not portion_ok then
        client_log(job_id, {
            operation = 'progress_set_portion_error',
            message = tostring(portion_message),
            completedNumber = completed_number,
            totalNumber = total_number,
        })
        return false
    end

    local caption_ok, caption_message = pcall(function()
        progress:setCaption(tostring(caption or ''))
    end)
    if not caption_ok then
        client_log(job_id, {
            operation = 'progress_set_caption_error',
            message = tostring(caption_message),
            caption = tostring(caption or ''),
        })
        return false
    end

    return true
end

local function apply_result(catalog, by_path, managed_keywords, result, job_id)
    local updated = 0
    local empty = 0
    local errors = 0
    local keywords = {}
    if result.state == 'ok' then
        for _, keyword_path in ipairs(dedupe_keywords(result.keywords or {})) do
            local ensured, ensure_message = ensure_keyword_path(catalog, keyword_path)
            if not ensured then
                client_log(job_id, {
                    operation = 'ensure_keyword_path_error',
                    path = result.path or '',
                    keyword = keyword_path,
                    message = ensure_message,
                })
                errors = errors + 1
            else
                table.insert(keywords, keyword_path)
            end
        end
    end

    local write_ok, write_result = LrTasks.pcall(function()
        return catalog:withWriteAccessDo('Apply Aves Caesar keywords', function()
            local photo = by_path[result.path]
            if photo ~= nil and result.state == 'ok' then
                local keyword_errors = 0
                remove_aves_keywords(photo, managed_keywords)

                for _, keyword_path in ipairs(keywords) do
                    local applied, message = apply_keyword_path(catalog, photo, keyword_path)
                    if not applied then
                        keyword_errors = keyword_errors + 1
                        client_log(job_id, {
                            operation = 'apply_keyword_error',
                            path = result.path,
                            keyword = keyword_path,
                            message = message,
                        })
                    end
                end

                if keyword_errors > 0 then
                    errors = errors + keyword_errors
                elseif errors > 0 then
                    updated = 0
                elseif #keywords > 0 then
                    updated = 1
                else
                    empty = 1
                end
            elseif result.state == 'error' then
                errors = 1
                client_log(job_id, {
                    operation = 'prediction_result_error',
                    path = result.path,
                    message = result.message or '',
                })
            end
        end)
    end)

    if not write_ok then
        client_log(job_id, {
            operation = 'with_write_access_exception',
            path = result.path or '',
            message = tostring(write_result),
        })
        errors = errors + 1
    end

    if write_result == 'aborted' then
        errors = errors + 1
        client_log(job_id, {
            operation = 'with_write_access',
            path = result.path or '',
            message = tostring(write_result),
        })
    end

    return updated, empty, errors
end

local function apply_results(catalog, photos, results, job_id)
    local by_path = {}
    for _, photo in ipairs(photos) do
        by_path[photo_path(photo)] = photo
    end

    local managed_keywords = aves_managed_keywords(catalog)
    local updated = 0
    local empty = 0
    local errors = 0
    for _, result in ipairs(results) do
        local just_updated, just_empty, just_errors = apply_result(catalog, by_path, managed_keywords, result, job_id)
        updated = updated + just_updated
        empty = empty + just_empty
        errors = errors + just_errors
    end

    return updated, empty, errors
end

local function wait_for_job(job_id, total, catalog, photos)
    local progress = LrProgressScope { title = 'Aves Caesar Lightroom tagging' }
    local status = nil
    local applied = {}
    local updated = 0
    local empty = 0
    local apply_errors = 0
    repeat
        status = request_json('GET', '/jobs/' .. job_id .. '/status')
        local payload = request_json('GET', '/jobs/' .. job_id .. '/results')
        local pending_results = {}
        for _, result in ipairs(payload.results or {}) do
            if applied[result.path] ~= true then
                table.insert(pending_results, result)
                applied[result.path] = true
            end
        end

        if #pending_results > 0 then
            local just_updated, just_empty, just_errors = apply_results(catalog, photos, pending_results, job_id)
            updated = updated + just_updated
            empty = empty + just_empty
            apply_errors = apply_errors + just_errors
        end

        local completed = numeric_value(status.completed, 0)
        local total_number = numeric_value(total, 0)
        local errors = numeric_value(status.errors, 0) + apply_errors
        local eta = status.etaSeconds
        local caption = tostring(completed) .. '/' .. tostring(total_number) .. ' processed, ' .. tostring(errors) .. ' error(s)'
        if eta ~= nil then
            caption = caption .. ', ETA ' .. format_duration(eta)
        end

        update_progress(job_id, progress, completed, total_number, caption)
        LrTasks.sleep(0.5)
    until status.state ~= 'running'
    progress:done()
    return status, updated, empty, apply_errors
end

function Aves.openPanel()
    local action = present_action_panel()
    if action == 'tag_selected' then
        Aves.run('selected')
        return
    end

    if action == 'tag_active_folder' then
        Aves.run('active_folder')
        return
    end

    if action == 'tag_entire_catalog' then
        Aves.run('entire_catalog')
        return
    end

    if action == 'clear_active_folder' then
        Aves.clear('active_folder')
        return
    end

    if action == 'clear_entire_catalog' then
        Aves.clear('entire_catalog')
    end
end

function Aves.run(mode)
    LrTasks.startAsyncTask(function()
        local catalog = LrApplication.activeCatalog()
        local initial_photos = photos_for_mode(catalog, mode, true)
        if initial_photos == nil then
            LrDialogs.message('Aves Caesar', 'Select one or more folders in the Folders panel first.', 'info')
            return
        end

        if #initial_photos == 0 then
            LrDialogs.message('Aves Caesar', 'No photos found for this command.', 'info')
            return
        end

        local options = present_options(mode, #initial_photos)
        if options == nil then
            return
        end

        local photos = photos_for_mode(catalog, mode, options.includeChildren)
        if photos == nil or #photos == 0 then
            LrDialogs.message('Aves Caesar', 'No photos found for this command.', 'info')
            return
        end

        if mode == 'entire_catalog' then
            local confirm = LrDialogs.confirm('Tag the entire catalog (' .. tostring(#photos) .. ' photos)?', 'This can take a long time.', 'Start', 'Cancel')
            if confirm ~= 'ok' then
                return
            end
        end

        local skipped_existing = 0
        photos, skipped_existing = photos_without_aves_keywords(photos)
        if #photos == 0 then
            LrDialogs.message('Aves Caesar', 'All selected photos already have Aves Caesar keywords. Nothing to process.', 'info')
            return
        end

        local files = {}
        for _, photo in ipairs(photos) do
            table.insert(files, photo_path(photo))
        end

        local start = request_json('POST', '/jobs', {
            files = files,
            language = options.language,
            reprocess = options.reprocess,
            context = mode,
            gpxPaths = options.gpxPaths,
        })
        local job_id = start.jobId
        local status, updated, empty, apply_errors = wait_for_job(job_id, #files, catalog, photos)
        local errors = numeric_value(status.errors, 0) + apply_errors
        local duration = status.elapsedSeconds or 0
        LrDialogs.message('Aves Caesar', 'Processed: ' .. tostring(status.completed or 0) .. '\nUpdated: ' .. tostring(updated) .. '\nWithout Aves Caesar keyword: ' .. tostring(empty) .. '\nSkipped existing Aves Caesar keywords: ' .. tostring(skipped_existing) .. '\nErrors: ' .. tostring(errors) .. '\nDuration: ' .. tostring(duration) .. 's', 'info')
    end)
end

function Aves.clear(mode)
    LrTasks.startAsyncTask(function()
        local catalog = LrApplication.activeCatalog()
        local include_children = true
        local photos = photos_for_mode(catalog, mode, include_children)
        if photos == nil then
            LrDialogs.message('Aves Caesar', 'Select one or more folders in the Folders panel first.', 'info')
            return
        end

        if #photos == 0 then
            LrDialogs.message('Aves Caesar', 'No photos found for this command.', 'info')
            return
        end

        local target = mode == 'entire_catalog' and 'the entire catalog' or 'the active folder'
        local confirm = LrDialogs.confirm('Remove all Aves Caesar keywords from ' .. target .. ' (' .. tostring(#photos) .. ' photos)?', nil, 'Clear', 'Cancel')
        if confirm ~= 'ok' then
            return
        end

        local managed_keywords = aves_managed_keywords(catalog)
        if #managed_keywords == 0 then
            LrDialogs.message('Aves Caesar', 'No Aves Caesar keywords found.', 'info')
            return
        end

        local progress = LrProgressScope { title = 'Aves Caesar clear keywords' }
        local completed = 0
        local cleared = 0
        local clear_errors = 0
        local write_result = catalog:withWriteAccessDo('Clear Aves Caesar keywords', function()
            for _, photo in ipairs(photos) do
                local removed = remove_aves_keywords(photo, managed_keywords)
                if removed > 0 then
                    cleared = cleared + 1
                end
                completed = completed + 1
                update_progress(nil, progress, completed, #photos, tostring(completed) .. '/' .. tostring(#photos) .. ' cleared')
            end
        end)
        if write_result == 'aborted' then
            clear_errors = clear_errors + (#photos - completed)
        end
        progress:done()
        LrDialogs.message('Aves Caesar', 'Cleared Aves Caesar keywords from ' .. tostring(cleared) .. ' photo(s).\nErrors: ' .. tostring(clear_errors), 'info')
    end)
end

return Aves
