{
    "folke/twilight.nvim",

    lazy = false,

    dependencies = {
        "nvim-treesitter/nvim-treesitter",
    },

    opts = {
        dimming = {
            alpha = 0.25,
            color = { "Normal", "#ffffff" },
            term_bg = "#000000",
            inactive = false,
        },

        context = 10,
        treesitter = true,
    },

    config = function(_, opts)
        require("twilight").setup(opts)

        -- F4 toggles Twilight
        vim.keymap.set("n", "<F4>", "<cmd>Twilight<CR>", {
            silent = true,
            desc = "Toggle Twilight",
        })

        -- Wait until buffer setup/Treesitter has had time to attach
        local group = vim.api.nvim_create_augroup(
            "TwilightDeferredStartup",
            { clear = true }
        )

        vim.api.nvim_create_autocmd(
            { "BufReadPost", "BufNewFile" },
            {
                group = group,

                callback = function()
                    vim.schedule(function()
                        if vim.api.nvim_buf_is_valid(0) then
                            pcall(vim.cmd, "TwilightEnable")
                        end
                    end)
                end,
            }
        )
    end,
},
