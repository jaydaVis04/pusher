return {
    {
        "jake-stewart/multicursor.nvim",
        branch = "main",

        config = function()
            local mc = require("multicursor-nvim")

            mc.setup()

            local set = vim.keymap.set

            -- Add cursor at next matching word / visual selection
            set({ "n", "x" }, "<A-n>", function()
                mc.matchAddCursor(1)
            end, { desc = "Add next matching cursor" })

            -- Add cursor at previous matching word / visual selection
            set({ "n", "x" }, "<A-p>", function()
                mc.matchAddCursor(-1)
            end, { desc = "Add previous matching cursor" })

            -- Add cursor on line above
            set({ "n", "x" }, "<A-Up>", function()
                mc.lineAddCursor(-1)
            end, { desc = "Add cursor above" })

            -- Add cursor on line below
            set({ "n", "x" }, "<A-Down>", function()
                mc.lineAddCursor(1)
            end, { desc = "Add cursor below" })

            -- Normal Esc behavior when multicursor is NOT active
            set("n", "<Esc>", function()
                vim.cmd("nohlsearch")
            end, { silent = true })

            -- Esc behavior while multicursor IS active
            mc.addKeymapLayer(function(layerSet)
                layerSet("n", "<Esc>", function()
                    if not mc.cursorsEnabled() then
                        -- Cursors exist but were disabled:
                        -- re-enable them first.
                        mc.enableCursors()
                    else
                        -- Cursors are enabled:
                        -- collapse them back to one cursor.
                        mc.clearCursors()
                    end
                end)
            end)
        end,
    },
}
