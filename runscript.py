require("twilight").setup({
    context = 10,
})

vim.api.nvim_create_autocmd("FileType", {
    callback = function(args)
        local parser = vim.treesitter.get_parser(args.buf, nil, {
            error = false,
        })

        if parser then
            vim.cmd("TwilightEnable")
        else
            vim.cmd("TwilightDisable")
        end
    end,
})
