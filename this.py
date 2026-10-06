return {

    -- ============================================================
    -- Treesitter
    -- ============================================================
    {
        "nvim-treesitter/nvim-treesitter",

        branch = "master",
        lazy = false,
        build = ":TSUpdate",

        opts = {
            ensure_installed = {
                "lua",
                "vim",
                "vimdoc",
                "bash",
                "c",
                "cpp",
                "python",
                "json",
                "markdown",
                "markdown_inline",
            },

            auto_install = true,

            highlight = {
                enable = true,
                additional_vim_regex_highlighting = false,
            },

            indent = {
                enable = true,
            },
        },

        config = function(_, opts)
            require("nvim-treesitter.configs").setup(opts)
        end,
    },


    -- ============================================================
    -- Nvim Tree
    -- Ctrl-N toggles the tree
    -- ============================================================
    {
        "nvim-tree/nvim-tree.lua",

        keys = {
            {
                "<C-n>",
                "<cmd>NvimTreeToggle<CR>",
                desc = "Toggle NvimTree",
            },
        },

        opts = {
            view = {
                width = 30,
            },

            renderer = {
                group_empty = true,
            },
        },
    },


    -- ============================================================
    -- Twilight
    -- F4 toggles dimming
    -- ============================================================
    {
        "folke/twilight.nvim",

        lazy = false,

        dependencies = {
            "nvim-treesitter/nvim-treesitter",
        },

        config = function()
            require("twilight").setup({
                dimming = {
                    alpha = 0.25,
                    color = { "Normal", "#ffffff" },
                    term_bg = "#000000",
                    inactive = false,
                },

                context = 10,

                treesitter = true,
            })


            -- F4 toggles Twilight
            vim.keymap.set(
                "n",
                "<F4>",
                "<cmd>Twilight<CR>",
                {
                    silent = true,
                    desc = "Toggle Twilight",
                }
            )


            -- Wait until the buffer has opened and Treesitter
            -- has had a chance to initialize.
            local group = vim.api.nvim_create_augroup(
                "TwilightDeferredStartup",
                { clear = true }
            )

            vim.api.nvim_create_autocmd(
                { "BufReadPost", "BufNewFile" },
                {
                    group = group,

                    callback = function(args)
                        vim.schedule(function()

                            if not vim.api.nvim_buf_is_valid(args.buf) then
                                return
                            end

                            if vim.bo[args.buf].buftype ~= "" then
                                return
                            end

                            local parser_ok =
                                pcall(
                                    vim.treesitter.get_parser,
                                    args.buf
                                )

                            if parser_ok then
                                pcall(vim.cmd, "TwilightEnable")
                            end
                        end)
                    end,
                }
            )
        end,
    },


    -- ============================================================
    -- UFO Folding
    -- ============================================================
    {
        "kevinhwang91/nvim-ufo",

        dependencies = {
            "kevinhwang91/promise-async",
        },

        event = {
            "BufReadPost",
            "BufNewFile",
        },

        init = function()
            vim.o.foldcolumn = "1"
            vim.o.foldlevel = 99
            vim.o.foldlevelstart = 99
            vim.o.foldenable = true
        end,

        config = function()
            local ufo = require("ufo")

            ufo.setup({
                provider_selector = function()
                    return {
                        "treesitter",
                        "indent",
                    }
                end,
            })

            vim.keymap.set(
                "n",
                "zR",
                ufo.openAllFolds,
                {
                    desc = "Open all folds",
                }
            )

            vim.keymap.set(
                "n",
                "zM",
                ufo.closeAllFolds,
                {
                    desc = "Close all folds",
                }
            )
        end,
    },


    -- ============================================================
    -- Multicursor
    --
    -- Loads:
    -- ~/.config/nvim/lua/multicursor.lua
    -- ============================================================
    {
        import = "multicursor",
    },

}
