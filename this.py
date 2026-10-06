-- ============================================================
-- Basic Neovim setup
-- ============================================================

vim.g.mapleader = " "
vim.g.maplocalleader = "\\"

vim.opt.termguicolors = true

-- Recommended by nvim-tree
vim.g.loaded_netrw = 1
vim.g.loaded_netrwPlugin = 1


-- ============================================================
-- Bootstrap lazy.nvim
-- ============================================================

local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"

if not vim.uv.fs_stat(lazypath) then
    local out = vim.fn.system({
        "git",
        "clone",
        "--filter=blob:none",
        "--branch=stable",
        "https://github.com/folke/lazy.nvim.git",
        lazypath,
    })

    if vim.v.shell_error ~= 0 then
        vim.api.nvim_echo({
            { "Failed to clone lazy.nvim:\n", "ErrorMsg" },
            { out, "WarningMsg" },
        }, true, {})
        os.exit(1)
    end
end

vim.opt.rtp:prepend(lazypath)


-- ============================================================
-- Plugins
-- ============================================================

require("lazy").setup({

    -- --------------------------------------------------------
    -- Treesitter
    --
    -- Pin master because highlight = { enable = true } belongs
    -- to the old nvim-treesitter API.
    -- --------------------------------------------------------
    {
        "nvim-treesitter/nvim-treesitter",

        branch = "master",
        lazy = false,
        build = ":TSUpdate",

        main = "nvim-treesitter.configs",

        opts = {
            ensure_installed = {
                "lua",
                "vim",
                "vimdoc",
                "query",
                "bash",
                "c",
                "cpp",
                "python",
                "javascript",
                "typescript",
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
    },


    -- --------------------------------------------------------
    -- nvim-tree
    -- Ctrl-N toggles file tree
    -- --------------------------------------------------------
    {
        "nvim-tree/nvim-tree.lua",

        dependencies = {
            "nvim-tree/nvim-web-devicons",
        },

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


    -- --------------------------------------------------------
    -- Twilight
    -- F4 toggles Twilight
    -- Startup is deferred until Treesitter has had a chance
    -- to initialize for the current buffer.
    -- --------------------------------------------------------
    {
        "folke/twilight.nvim",

        lazy = false,

        dependencies = {
            "nvim-treesitter/nvim-treesitter",
        },

        opts = {
            treesitter = true,
            context = 10,
        },

        config = function(_, opts)
            require("twilight").setup(opts)

            -- Safe F4 toggle.
            --
            -- Check that this buffer actually has a Treesitter parser
            -- before asking Twilight to use it.
            vim.keymap.set("n", "<F4>", function()
                local ok = pcall(vim.treesitter.get_parser, 0)

                if not ok then
                    vim.notify(
                        "No Treesitter parser available for this buffer",
                        vim.log.levels.WARN
                    )
                    return
                end

                vim.cmd("Twilight")
            end, {
                silent = true,
                desc = "Toggle Twilight",
            })


            -- Automatically enable Twilight after opening a file.
            --
            -- vim.schedule() moves this until after the current startup /
            -- buffer event has completed, giving Treesitter time to attach.
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

                            -- Ignore terminals, help buffers, etc.
                            if vim.bo[args.buf].buftype ~= "" then
                                return
                            end

                            -- Do not start Twilight unless this buffer
                            -- actually has a valid Treesitter parser.
                            local parser_ok =
                                pcall(vim.treesitter.get_parser, args.buf)

                            if not parser_ok then
                                return
                            end

                            pcall(vim.cmd, "TwilightEnable")
                        end)
                    end,
                }
            )
        end,
    },


    -- --------------------------------------------------------
    -- nvim-ufo
    -- --------------------------------------------------------
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

        opts = {
            provider_selector = function()
                return { "treesitter", "indent" }
            end,
        },

        config = function(_, opts)
            local ufo = require("ufo")

            ufo.setup(opts)

            vim.keymap.set(
                "n",
                "zR",
                ufo.openAllFolds,
                { desc = "Open all folds" }
            )

            vim.keymap.set(
                "n",
                "zM",
                ufo.closeAllFolds,
                { desc = "Close all folds" }
            )
        end,
    },


    -- --------------------------------------------------------
    -- Import ~/.config/nvim/lua/multicursor.lua
    -- --------------------------------------------------------
    {
        import = "multicursor",
    },

})
