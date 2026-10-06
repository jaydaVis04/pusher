//before re_read
static int read_phys_ram(phys_addr_t phys, void *dst, size_t len)
{
    unsigned long pfn;
    unsigned long page_off;
    struct page *page;
    void *vaddr;

    pfn = PHYS_PFN(phys);
    page_off = offset_in_page(phys);

    if (!pfn_valid(pfn))
        return -EINVAL;

    if (page_off + len > PAGE_SIZE)
        return -EINVAL;

    page = pfn_to_page(pfn);

    vaddr = kmap(page);
    if (!vaddr)
        return -ENOMEM;

    memcpy(dst, (u8 *)vaddr + page_off, len);

    kunmap(page);

    return 0;
}

//corerect reread
static ssize_t re_read(struct file *file,
                       char __user *user_buffer,
                       size_t count,
                       loff_t *offset)
{
    u8 *tmp;
    size_t total = 0;
    size_t available;

    if (*offset < 0)
        return -EINVAL;

    if ((u64)*offset >= phys_size)
        return 0;

    available = phys_size - (size_t)*offset;

    if (count > available)
        count = available;

    if (!count)
        return 0;

    tmp = kmalloc(PAGE_SIZE, GFP_KERNEL);
    if (!tmp)
        return -ENOMEM;

    while (total < count) {
        phys_addr_t phys_cur;
        size_t page_remaining;
        size_t chunk;
        int ret;

        phys_cur = phys_base +
                   (phys_addr_t)*offset +
                   total;

        page_remaining =
            PAGE_SIZE - offset_in_page(phys_cur);

        chunk = count - total;

        if (chunk > page_remaining)
            chunk = page_remaining;

        ret = read_phys_ram(phys_cur, tmp, chunk);

        if (ret) {
            kfree(tmp);

            if (total) {
                *offset += total;
                return total;
            }

            return ret;
        }

        if (copy_to_user(user_buffer + total,
                         tmp,
                         chunk)) {
            kfree(tmp);

            if (total) {
                *offset += total;
                return total;
            }

            return -EFAULT;
        }

        total += chunk;
    }

    kfree(tmp);

    *offset += total;

    return total;
}
