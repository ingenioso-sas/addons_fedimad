# -*- coding: utf-8 -*-
##############################################################################
#                                                                            #
#    Odoo                                                                    #
#    Copyright (C) 2022-2023 Feddad Imad (feddad.imad@gmail.com)             #
#                                                                            #
##############################################################################

import os
import csv
import tempfile
from odoo.exceptions import UserError
from odoo import api, fields, models, _, SUPERUSER_ID
from datetime import datetime, timedelta, date
import xlrd, mmap, xlwt
import base64



class ImportPurchaseOrder(models.TransientModel):
    _name = "wizard.import.purchase.order"

    file_data = fields.Binary('Archive', required=True,)
    file_name = fields.Char('File Name')
    id_field = fields.Selection(selection=[('codigo', 'codigo'),('nombre', 'nombre')], required=True, default="codigo")
    partner_id = fields.Many2one('res.partner', string='Partner', required=True, domain=[('customer_rank', '>', 0)])


    def import_button(self):
        if not self.csv_validator(self.file_name):
            raise UserError(_("The file must be an .xls/.xlsx extension"))
        file_path = tempfile.gettempdir()+'/file.xlsx'
        data = self.file_data
        f = open(file_path,'wb')
        f.write(base64.b64decode(data))
        f.close() 


        workbook = xlrd.open_workbook(file_path, on_demand = True)
        worksheet = workbook.sheet_by_index(0)
        first_row = [] # The row where we stock the name of the column
        for col in range(worksheet.ncols):
            first_row.append( worksheet.cell_value(0,col) )
        # transform the workbook to a list of dictionaries
        archive_lines = []
        for row in range(1, worksheet.nrows):
            elm = {}
            for col in range(worksheet.ncols):
                elm[first_row[col]]=worksheet.cell_value(row,col)

            archive_lines.append(elm)

        purchase_order_obj = self.env['purchase.order']
        product_obj = self.env['product.product']
        product_template_obj = self.env['product.template']
        purchase_order_line_obj = self.env['purchase.order.line']

        self.valid_columns_keys(archive_lines)
        self.valid_product_code(archive_lines, product_obj)
        self.valid_prices(archive_lines)
        
        vals = {
            'partner_id': self.partner_id.id,
            'date_planned': datetime.now(),
        }
        purchase_order_id = purchase_order_obj.create(vals)
        cont = 0
        for line in archive_lines:
            cont += 1
            if (self.id_field == "nombre"):
                product_name = str(line.get('nombre',"")).strip()
                product_id = product_obj.search([('name','=',product_name)])
            else:
                posible_numero = str(line.get('codigo',"")).strip()
                if(posible_numero.isnumeric()):
                    posible_numero = str(int(posible_numero))
                code = posible_numero
                product_id = product_obj.search([('default_code','=',code)])
                
            quantity = line.get(u'cantidad',0)
            price_unit = self.get_valid_price(line.get('costo',""),cont)
            # product_uom = product_template_obj.search([('default_code','=',code)])
            taxes = product_id.supplier_taxes_id.filtered(lambda r: not product_id.company_id or r.company_id == product_id.company_id)
            tax_ids = taxes.ids
            if purchase_order_id and product_id:
                vals = {
                    'order_id': purchase_order_id.id,
                    'product_id': product_id.id,
                    'product_qty': float(quantity),
                    'price_unit': price_unit,
                    'date_planned': datetime.now(),
                    'product_uom': product_id.product_tmpl_id.uom_po_id.id,
                    'name': product_id.name,
                    'taxes_id' : [(6,0,tax_ids)],
                }
                purchase_order_line_obj.create(vals)
        if self._context.get('open_order', False):
            return purchase_order_id.action_view_order(purchase_order_id.id)
        return {'type': 'ir.actions.act_window_close'}

        
    @api.model
    def valid_prices(self, archive_lines):
        cont = 0
        for line in archive_lines:
            cont += 1
            price = line.get('costo',"")
            if price != "":
                price = str(price).replace("$","").replace(",",".")
            try:
                price_float = float(price)
            except:
                raise UserError("The price of the line item %s does not have an appropriate format, for example: '100.00' - '100'"%cont)

        return True

    @api.model
    def get_valid_price(self, price, cont):
        if price != "":
            price = str(price).replace("$","").replace(",",".")
        try:
            price_float = float(price)
            return price_float
        except:
            raise UserError("The price of the line item %s does not have an appropriate format, for example: '100.00' - '100'"%cont)
        return False

    @api.model
    def valid_product_code(self, archive_lines, product_obj):
        cont=0
        for line in archive_lines:
            cont += 1
            product_name = None
            code = None
            error_message = "Error desconocido ..."
            if (self.id_field == "nombre"):
                product_name = str(line.get('nombre',"")).strip()
                product_id = product_obj.search([('name','=',product_name)])
            else:
                posible_numero = str(line.get('codigo',"")).strip()
                if(posible_numero.isnumeric()):
                    posible_numero = str(int(posible_numero))
                code = posible_numero
                product_id = product_obj.search([('default_code','=',code)])
            
            if(product_name):
                error_message = "Nombre del producto: " + product_name
            if(code):
                error_message = "Codigo del producto: " + code

            if len(product_id)>1:
                raise UserError( error_message + " de la linea %s is duplicado en el sistema."%cont)
            if not product_id:
                raise UserError( error_message + " de la linea %s no pudo ser encontrado en el sistema."%cont)

    @api.model
    def valid_columns_keys(self, archive_lines):
        columns = archive_lines[0].keys()
       # print "columns>>",columns
        text = "The file must contain the following columns: code, quantity, and price. \n The following columns are not in the file:"; text2 = text
        if not 'codigo' in columns and not 'nombre' in columns:
            text +="\n[ codigo ] o [ nombre ]"
        if not u'cantidad' in columns:
            text +="\n[ cantidad ]"
        if not 'costo' in columns:
            text +="\n[ costo ]"
        if text !=text2:
            raise UserError(text)
        return True

    @api.model
    def csv_validator(self, xml_name):
        name, extension = os.path.splitext(xml_name)
        return True if extension == '.xls' or extension == '.xlsx' else False
        

class purchase_order(models.Model):
    _inherit = 'purchase.order'


    def action_view_order(self,purchase_order_id):
        action = self.env.ref('purchase.purchase_rfq').read()[0]
        action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
        action['res_id'] = purchase_order_id

        return action  

